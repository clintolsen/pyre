#!/usr/bin/env python

from __future__ import annotations

import functools
import logging
import weakref

LOG = logging.getLogger(__name__)

# Patterns match code points, but the DFA reads UTF-8 bytes, so its alphabet
# and character sets stay at 256. A class of code points derives by a byte
# to the rest of each character it can start, and ~r is relative to valid
# UTF-8, so every pattern matches only whole, valid characters. Surrogates
# count as characters, as Python's 'surrogatepass' encodes them.
#
CHARSET_MAX = (1 << 256)
MAX_CODE_POINT = 0x10FFFF

# A derivative of an RE 'r' with respect to a character 'a' is:
#
# ∂𝑎(r)
#
# and a nullable function denoted by:
#
# ν(r) = ε if r is nullable (True) ...
#        0 otherwise
#
# The numbered simplification rules in each constructor are the similarity
# rules from Owens, Reppy and Turon, "Regular-expression derivatives
# reexamined", except for ⊕, which the paper does not have. Each constructor
# applies them in whatever order suits it, so the numbers are references,
# not a sequence.
#
class Regex:
    '''Base class for all regular expression objects'''

    # Equal expressions are one object, so comparing them is `is`. The
    # table holds its nodes weakly: a node lives while something uses it,
    # and building an equal one meanwhile finds it again. Its key holds the
    # operands, so they live as long as the node does.
    #
    _instance = weakref.WeakValueDictionary()
    _id_count = 0

    @classmethod
    def _intern(cls, key, init):
        """
        init(self) should set all subclass-specific attributes.
        This method handles caching + all base defaults exactly once.
        """
        try:
            return Regex._instance[key]
        except KeyError:
            self = object.__new__(cls)
            self.key = key

            Regex._id_count += 1
            self.id = Regex._id_count

            self._nullable = None
            self._isnullable = None
            self._derivatives = {}
            self._stripped = None

            # The capture pass's caches, kept here so they go with the node
            #
            self._branches = {}
            self._markers = None
            self.events = ()

            # The operands of this node, in order. Every walk over the tree
            # goes through args, so |, & and · nodes, which keep their
            # operands flattened, are one level deep however many operands
            # they have.
            #
            self.args = ()

            self.isempty = False
            self.isepsilon = False
            self.ismarker = False
            self.isstar = False
            self.isplus = False
            self.isopt = False
            self.isdot = False
            self.isany = False
            self.isnot = False

            init(self)

            # True if a capture marker appears anywhere below this node.
            # Simplifications and interning that are fine for the language
            # must not reorder or drop such terms.
            #
            self.hascaptures = self.ismarker or any(arg.hascaptures for arg in self.args)

            Regex._instance[key] = self
            return self

    def nullable(self):
        return RegexEmpty()

    # Kept as a flag, since nullable() on a leaf builds ∅ again each time,
    # and subsumption asks this of every operand it compares
    #
    def isnullable(self):
        if self._isnullable is None:
            self._isnullable = self.nullable().isepsilon
        return self._isnullable

    # Nodes are interned and immutable, so each derivative is computed once
    # per character and kept. Derivatives share subterms, and without this
    # the shared parts are derived again along every path that reaches them,
    # which grows exponentially with nested stars such as (a(a(a)*)*)*.
    #
    def derive(self, ch):
        try:
            return self._derivatives[ch]
        except KeyError:
            result = self._derivatives[ch] = self._derive(ch)
            return result

    def _derive(self, ch):
        raise NotImplementedError(f'{type(self).__name__}._derive')

    __hash__ = object.__hash__
    def __eq__(self, other):
        return self is other

    # Return a copy with every capture marker replaced by ε. Markers are
    # zero-width, so the language is unchanged.
    #
    # Set operators keep markers, so composed patterns report the groups of
    # whichever operand matched. pyre.equal() and pyre.subset() strip them
    # first purely as an optimization: markers make otherwise identical terms
    # distinct, which adds DFA states and defeats the r ^ r = ∅ shortcut for
    # separately parsed copies of one pattern.
    #
    def _without_captures(self):
        if not self.hascaptures:
            return self
        if self.ismarker:
            return RegexEpsilon()
        if self._stripped is None:
            args = [arg._without_captures() for arg in self.args]
            if len(args) == 1:
                self._stripped = self.__class__(args[0])
            else:
                self._stripped = functools.reduce(self.__class__, args)
        return self._stripped

    def __or__(self, other):
        if not isinstance(other, Regex):
            return NotImplemented
        return RegexOr(self, other)

    def __ror__(self, other):
        if not isinstance(other, Regex):
            return NotImplemented
        return RegexOr(other, self)

    def __and__(self, other):
        if not isinstance(other, Regex):
            return NotImplemented
        return RegexAnd(self, other)

    def __rand__(self, other):
        if not isinstance(other, Regex):
            return NotImplemented
        return RegexAnd(other, self)

    def __xor__(self, other):
        if not isinstance(other, Regex):
            return NotImplemented
        return RegexXor(self, other)

    def __rxor__(self, other):
        if not isinstance(other, Regex):
            return NotImplemented
        return RegexXor(other, self)

    def __sub__(self, other):
        if not isinstance(other, Regex):
            return NotImplemented
        return RegexDiff(self, other)

    def __rsub__(self, other):
        if not isinstance(other, Regex):
            return NotImplemented
        return RegexDiff(other, self)

    def __invert__(self):
        return RegexNot(self)

    # Allow for use in boolean contexts. If we're not empty, then we are True.
    #
    def __bool__(self):
        return not self.isempty

    def __repr__(self):
        rep = '<%s %s=0x%x' % (self.__class__.__name__, self.id, id(self))
        for arg in self.args:
            rep += ' 0x%x' % id(arg)
        if hasattr(self, 'sym'):
            rep += ' %s' % repr(self.sym)
        rep += f' events={self.events}'
        rep += '>'

        return rep

    # Rank precedence values for each tree type, matching the parser
    #
    PRECEDENCE = {
        'RegexOr': 1,
        'RegexDiff': 1,
        'RegexXor': 1,
        'RegexAnd': 2,
        'RegexConcat': 5,
        'RegexNot': 6,
        'RegexStar': 7,
        'RegexPlus': 7,
        'RegexOpt': 7,
        'RegexRepeat': 7,
    }

    # Operators where (a op b) op c and a op (b op c) are the same
    #
    ASSOCIATIVE = {'RegexOr', 'RegexAnd', 'RegexXor', 'RegexConcat'}

    def paren(self, child, right=False):
        '''
        Emit parens if the child binds more loosely than the parent. Binary
        operators group left to right, so a right operand at the same level
        needs them too, unless it is the same associative operator.
        '''
        self_class = self.__class__.__name__
        child_class = child.__class__.__name__

        # __str__ directly rather than str(), and a loop in join() rather
        # than a generator, so printing takes three frames per level of the
        # tree and deep trees print within the default recursion limit
        #
        text = child.__str__()

        try:
            mine = Regex.PRECEDENCE[self_class]
            theirs = Regex.PRECEDENCE[child_class]
        except KeyError:
            return text

        if theirs < mine or (right and theirs == mine and not (
                child_class == self_class and self_class in Regex.ASSOCIATIVE)):
            return f'({text})'

        return text

    def join(self, sep):
        ''' The operands printed between separators, grouped left to right '''
        parts = []
        for i, arg in enumerate(self.args):
            parts.append(self.paren(arg, right=i > 0))
        return sep.join(parts)

    def tree(self, prefix='', is_last=True):
        ''' Output a representation of an RE as an ASCII tree '''
        out = ''
        if prefix:
            if is_last:
                out += prefix[:-4] + '└── '
            else:
                out += prefix[:-4] + '├── '
        out += repr(self) + '\n'

        # Last operand first, so the first one ends the tree
        #
        for i, arg in enumerate(reversed(self.args)):
            is_last = i == len(self.args) - 1
            out += prefix + '│    \n'
            out += arg.tree(prefix=prefix + ('    ' if is_last else '│   '), is_last=is_last)

        return out

    # Walk an expr and apply a function (code) on each element
    #
    def walk(self, code):
        # work on this object
        #
        code(self)

        # Walk to the children
        #
        for arg in self.args:
            arg.walk(code)


    @staticmethod
    def unique(args):
        ''' Drop repeated arguments, keeping the first occurrence of each in order '''
        seen = set()
        out = []
        for arg in args:
            if arg not in seen:
                seen.add(arg)
                out.append(arg)
        return out

    @staticmethod
    def _subsumes(x, y):
        '''
        True if every string y matches x does too, as seen from their
        operands. After a prefix u the two share, either x is u·p·s and y is
        u·s, or x is u·p·.* and y is u followed by anything, where p is
        nullable in both cases. u and p may be empty.
        '''
        if y.isepsilon:
            return x.isnullable()

        xs = x.args if isinstance(x, RegexConcat) else (x,)
        ys = y.args if isinstance(y, RegexConcat) else (y,)
        if xs[0] is not ys[0] and not xs[0].isnullable():
            return False

        # The longest shared prefix is enough: anything a shorter one would
        # leave in p is also nullable
        #
        n = 0
        while n < len(xs) - 1 and n < len(ys) and xs[n] is ys[n]:
            n += 1

        if xs[-1].isany:
            return all(p.isnullable() for p in xs[n:-1])

        k = len(xs) - len(ys)
        return k > 0 and xs[n + k:] == ys[n:] and all(p.isnullable() for p in xs[n:n + k])

    @staticmethod
    def _may_subsume(expr):
        '''
        False if no alternative in expr can subsume another: that takes one
        that is nullable or a concatenation with a nullable operand. Keyword
        lists never qualify, so this skips the check.
        '''
        if isinstance(expr, RegexOr):
            return expr.may_subsume
        return expr.isnullable() or (isinstance(expr, RegexConcat) and
                                     any(arg.isnullable() for arg in expr.args))

    @staticmethod
    def _subsumed(xs, ys):
        '''
        The alternatives in ys that some alternative in xs subsumes. Only a
        concatenation can subsume anything but ε, and only one that ends the
        way y does or ends in .*, so xs is indexed by last operand, with
        None for .*.
        '''
        ends = {}
        for x in xs:
            if isinstance(x, RegexConcat):
                last = None if x.args[-1].isany else x.args[-1]
                ends.setdefault(last, []).append(x)
        anys = ends.get(None, [])

        out = set()
        for y in ys:
            if y.isepsilon:
                candidates = xs
            else:
                candidates = ends.get(y.args[-1] if isinstance(y, RegexConcat) else y, [])
                if anys:
                    candidates = candidates + anys
            for x in candidates:
                if x is not y and Regex._subsumes(x, y) and Regex._keeps(x, y):
                    out.add(y)
                    break
        return out

    @staticmethod
    def _keeps(x, y):
        '''
        True if x should stay in place of y, once x is known to subsume y.
        When y also subsumes x, as x·.* and x·a*·.* do, the two are the same
        language, so this keeps the one with fewer operands, or the older
        one, whichever side of the | each is on.
        '''
        if not Regex._subsumes(y, x):
            return True
        return (len(x.args), x.id) < (len(y.args), y.id)

    @staticmethod
    def get_args(expr, expr_type):
        '''
        The operands of expr as a flat list if it is an expr_type node, so
        (a·b)·c gives [a, b, c]; otherwise [expr]. Each |, & and · node keeps
        its flattened operands from when it was built, so nothing is walked.
        Walking was quadratic for long chains, and exponential when an
        alternation was rebuilt from overlapping alternations.
        '''
        if isinstance(expr, expr_type):
            return list(expr.args)
        return [expr]


class RegexEmpty(Regex):
    '''Empty or null set.

    ∂𝑎(0) = 0
    ν(0) = 0 (False)

    '''
    sym = '∅'

    def __new__(cls, **kwargs):
        key = (cls, frozenset(kwargs.items()))

        def init(self):
            self.charset = CharSet(CHARSET_MAX - 1)
            self.isempty = True

        return cls._intern(key, init)

    def _derive(self, ch):
        return self

    def __str__(self):
        return RegexEmpty.sym


class RegexEpsilon(Regex):
    '''Epsilon aka empty string: ε

    ∂𝑎(ε) = 0
    ν(ε) = ε (True)

    '''
    sym = 'ε'

    def __new__(cls, **kwargs):
        key = (cls, frozenset(kwargs.items()))

        def init(self):
            self.charset = CharSet(CHARSET_MAX - 1)
            self.isepsilon = True
            return self

        return cls._intern(key, init)

    def nullable(self):
        return self

    def _derive(self, ch):
        return RegexEmpty()

    def __str__(self):
        return RegexEpsilon.sym

def merge_ranges(ranges, closed=True):
    '''
    Sorted, disjoint (lo, hi) ranges covering the same values. Ranges are
    closed by default, so (1, 2) and (3, 4) merge; with closed=False they
    are half-open spans, like match offsets, and merge only when they touch.
    '''
    gap = 1 if closed else 0
    out = []
    for lo, hi in sorted(ranges):
        if out and lo <= out[-1][1] + gap:
            if hi > out[-1][1]:
                out[-1] = (out[-1][0], hi)
        else:
            out.append((lo, hi))
    return tuple(out)


def mask_ranges(mask):
    ''' The set bits of mask as sorted, disjoint (lo, hi) ranges '''
    out = []
    lo = 0
    while mask:
        skip = (mask & -mask).bit_length() - 1
        mask >>= skip
        lo += skip
        run = (~mask & (mask + 1)).bit_length() - 1
        out.append((lo, lo + run - 1))
        mask >>= run
        lo += run
    return tuple(out)


def invert_ranges(ranges):
    ''' The code points not in ranges, as sorted, disjoint ranges '''
    out = []
    start = 0
    for lo, hi in merge_ranges(ranges):
        if lo > start:
            out.append((start, lo - 1))
        start = hi + 1
    if start <= MAX_CODE_POINT:
        out.append((start, MAX_CODE_POINT))
    return tuple(out)


def _encode(code):
    return chr(code).encode('utf-8', 'surrogatepass')


def _byte_mask(lo, hi):
    return ((1 << (hi + 1)) - 1) ^ ((1 << lo) - 1)


def utf8_sequences(lo, hi):
    '''
    Split the code points lo..hi into runs whose UTF-8 encodings are all
    the byte strings taking one byte from each of a list of ranges. Returns
    the runs, lowest first, each as a tuple of (low, high) byte ranges, so
    0x3B1..0x3C9 (α-ω) gives ((0xCE, 0xCE), (0xB1, 0xBF)) and
    ((0xCF, 0xCF), (0x80, 0x89)).
    '''
    out = []
    todo = [(lo, hi)]

    while todo:
        lo, hi = todo.pop()

        # Encodings of different lengths go in separate runs
        #
        for top in (0x7F, 0x7FF, 0xFFFF):
            if lo <= top < hi:
                todo += [(top + 1, hi), (lo, top)]
                break
        else:
            # Each byte after the first carries six bits, and has to range
            # over all of them or stay fixed, so split wherever the bits
            # below it would only partly wrap
            #
            for shift in (6, 12, 18):
                low = (1 << shift) - 1
                if lo & ~low == hi & ~low:
                    continue
                if lo & low:
                    todo += [((lo | low) + 1, hi), (lo, lo | low)]
                    break
                if hi & low != low:
                    todo += [(hi & ~low, hi), (lo, (hi & ~low) - 1)]
                    break
            else:
                out.append(tuple(zip(_encode(lo), _encode(hi))))

    return out


# Characters printed with a backslash: outside a class, those the parser
# reads as syntax; inside one, those it reads as class syntax
#
_SPECIAL = frozenset('\\.[](){}|^-&*+?~#ε')
_CLASS_SPECIAL = frozenset('\\]-^')

_NAMED_ESCAPES = {'\t': 't', '\n': 'n', '\r': 'r', '\v': 'v', '\f': 'f', '\a': 'a', ' ': ' '}


def _fmt_code_point(code, special):
    ch = chr(code)
    if ch in _NAMED_ESCAPES:
        return '\\' + _NAMED_ESCAPES[ch]
    if ch in special:
        return '\\' + ch
    if ch.isprintable():
        return ch
    if code < 0x100:
        return f'\\x{code:02x}'
    if code < 0x10000:
        return f'\\u{code:04x}'
    return f'\\U{code:08x}'


def _fmt_byte(code, special):
    return _fmt_code_point(code, special) if code < 0x80 else f'\\x{code:02x}'


def _fmt_ranges(ranges, fmt=_fmt_code_point):
    parts = []
    for lo, hi in ranges:
        parts.append(fmt(lo, _CLASS_SPECIAL))
        if hi > lo + 1:
            parts.append('-')
        if hi > lo:
            parts.append(fmt(hi, _CLASS_SPECIAL))
    return ''.join(parts)


class RegexCodePoints(Regex):
    '''
    A set of code points, matched as UTF-8 bytes.

    ∂𝑎(C) = ε if 𝑎 is an ASCII byte of C
            the bytes that complete C's characters starting with 𝑎, if any
            0 otherwise
    ν(C) = 0 (False)
    '''

    def _set_ranges(self, ranges):
        self.ranges = ranges

        # ASCII members derive to ε, and every lead byte to the rest of the
        # characters it starts, so bytes sharing a derivative share a class
        #
        ascii = 0
        tails = {}
        for lo, hi in ranges:
            for seq in utf8_sequences(lo, hi):
                first = seq[0]
                if len(seq) == 1:
                    ascii |= _byte_mask(*first)
                    continue
                tail = RegexConcat.of([RegexByte(_byte_mask(*rng)) for rng in seq[1:]])
                for byte in range(first[0], first[1] + 1):
                    tails.setdefault(byte, []).append(tail)

        self._ascii = ascii
        self._tails = {byte: functools.reduce(RegexOr, ts) for byte, ts in tails.items()}

        classes = {}
        for byte, tail in self._tails.items():
            classes[tail] = classes.get(tail, 0) | 1 << byte

        # Everything else derives to ∅
        #
        rest = (CHARSET_MAX - 1) ^ ascii
        for mask in classes.values():
            rest ^= mask
        self.charset = CharSet(ascii, rest, *classes.values())

    def _derive(self, ch):
        byte = ord(ch)
        if byte < 0x80:
            return RegexEpsilon() if self._ascii >> byte & 1 else RegexEmpty()
        return self._tails.get(byte, RegexEmpty())


class RegexSym(RegexCodePoints):
    '''
    Represents a character literal or character class.

    sym is a single character, or an iterable of (lo, hi) code point ranges.
    If 'negate' is False, this matches any character in the set.
    If 'negate' is True, this matches any character NOT in the set.
    '''

    def __new__(cls, sym, negate=False, **kwargs):
        if isinstance(sym, str):
            if len(sym) != 1:
                raise ValueError("RegexSym expects a single character string")
            ranges = ((ord(sym), ord(sym)),)
        else:
            ranges = merge_ranges(sym)

        if negate:
            ranges = invert_ranges(ranges)

        if not ranges:
            return RegexEmpty()
        if ranges == ((0, MAX_CODE_POINT),):
            return RegexDot()

        key = (cls, ranges, frozenset(kwargs.items()))

        def init(self):
            self._set_ranges(ranges)
            lo, hi = ranges[0]
            self.sym = chr(lo) if len(ranges) == 1 and lo == hi else None

        return cls._intern(key, init)

    def __str__(self):
        if self.sym is not None:
            return _fmt_code_point(ord(self.sym), _SPECIAL)

        inside = _fmt_ranges(self.ranges)
        outside = _fmt_ranges(invert_ranges(self.ranges))
        if len(outside) < len(inside):
            return f'[^{outside}]'
        return f'[{inside}]'


class RegexByte(Regex):
    '''
    A set of bytes. These only appear in derivatives, as the rest of a
    character whose first bytes were already read.

    ∂𝑎(B) = ε if 𝑎 in B, else 0
    ν(B) = 0 (False)
    '''

    def __new__(cls, mask, **kwargs):
        key = (cls, mask, frozenset(kwargs.items()))

        def init(self):
            self.mask = mask
            self.charset = CharSet(mask, (CHARSET_MAX - 1) ^ mask)

        return cls._intern(key, init)

    def _derive(self, ch):
        return RegexEpsilon() if self.mask >> ord(ch) & 1 else RegexEmpty()

    def __str__(self):
        return CharSet.fmt_mask(self.mask)

class RegexOr(Regex):
    '''Set union (OR): r | s - Match RE r or RE s

    ∂𝑎(r+s) = ∂𝑎(r) + ∂𝑎(s)
    ν(r+s) = ν(r) + ν(s)

    '''
    sym = '|'

    def __new__(cls, left, right, **kwargs):
        ''' Create an OR '''

        # 4) ¬∅ + r ≈ ¬∅
        #    r + ¬∅ ≈ ¬∅
        #
        # A capturing r on the left still has priority over ¬∅ on the
        # right, so (a)|.* must keep reporting group 1 for "a".
        #
        if left.isany or (right.isany and not left.hascaptures):
            return RegexStar(RegexDot())

        # 5) ∅ + r ≈ r
        #    r + ∅ ≈ r
        #
        if left.isempty:
            return right
        if right.isempty:
            return left

        # 1) r + r ≈ r
        #
        if left is right:
            return left

        args_l = Regex.get_args(left, RegexOr)
        args_r = Regex.get_args(right, RegexOr)
        args_u = Regex.unique(args_l + args_r)

        # Alternatives with capture groups are ordered: the left one numbers
        # its groups first and wins when both match. Everything else stays
        # commutative so DFA states still treat r + s and s + r as one.
        #
        ordered = left.hascaptures or right.hascaptures

        if set(args_r) <= set(args_l):
            return left
        if set(args_l) <= set(args_r):
            if not ordered or args_u == Regex.unique(args_r):
                return right

        # Beyond the paper's rules, s + p·s ≈ p·s when p is nullable, since
        # then L(s) ⊆ L(p·s). ε + r ≈ r when r is nullable is the case where
        # s is empty. Both sides may also start with the same prefix u, and
        # u·t + u·p·.* ≈ u·p·.* for any t. This only shrinks DFAs; the
        # paper's rules are what make them finite. Only without captures,
        # where dropping an alternative cannot change which one reports
        # groups.
        #
        # Each side was already reduced when it was built, so only pairs
        # with one alternative from each side need checking. Checking every
        # pair made large alternations cubic to build.
        #
        if not ordered:
            dropped = set()
            if Regex._may_subsume(right):
                dropped |= Regex._subsumed(args_r, args_l)
            if Regex._may_subsume(left):
                dropped |= Regex._subsumed(args_l, args_r)
            if dropped:
                return functools.reduce(RegexOr, [y for y in args_u if y not in dropped])

        # 2) r + s ≈ s + r, unless captures make order matter
        #
        args = tuple(args_u)
        if ordered:
            key = (cls, args, frozenset(kwargs.items()))
        else:
            key = (cls, frozenset(args), frozenset(kwargs.items()))

        def init(self):
            self.args = args
            self.charset = left.charset & right.charset
            self.may_subsume = Regex._may_subsume(left) or Regex._may_subsume(right)

        return cls._intern(key, init)

    def nullable(self):
        if self._nullable is None:
            if any(arg.isnullable() for arg in self.args):
                self._nullable = RegexEpsilon()
            else:
                self._nullable = RegexEmpty()

        return self._nullable

    def _derive(self, ch):
        return functools.reduce(RegexOr, [arg.derive(ch) for arg in self.args])

    def __str__(self):
        return self.join(f' {RegexOr.sym} ')


class RegexXor(Regex):
    '''Set (XOR): r ⊕ s - Match RE r xor RE s

    ∂𝑎(r+s) = ∂𝑎(r) ⊕ ∂𝑎(s)
    ν(r⊕s) = ν(r) ⊕ ν(s)

    '''
    sym = '^'

    def __new__(cls, left, right, **kwargs):
        ''' Create an XOR '''

        # 3) r ⊕ r = ∅
        #
        if left is right:
            return RegexEmpty()

        # 1) ∅ ⊕ r = r
        #
        if left.isempty:
            return right

        # 2) r ⊕ ∅ = r
        #
        if right.isempty:
            return left

        # Only one side can match, so order never sets priority, but it
        # still sets group numbering when either side has captures.
        #
        if left.hascaptures or right.hascaptures:
            args = (left, right)
            key = (cls, args, frozenset(kwargs.items()))
        else:
            # 4) ⊕ is associative and commutative, and r ⊕ r = ∅, so the
            #    operands flatten into one node, and an operand that occurs
            #    twice cancels out. A chain of ⊕ is one level deep.
            #
            odd = {}
            for arg in Regex.get_args(left, RegexXor) + Regex.get_args(right, RegexXor):
                if odd.pop(arg, None) is None:
                    odd[arg] = True
            if not odd:
                return RegexEmpty()
            if len(odd) == 1:
                return next(iter(odd))
            args = tuple(odd)
            key = (cls, frozenset(args), frozenset(kwargs.items()))

        def init(self):
            self.args = args
            self.charset = left.charset & right.charset

        return cls._intern(key, init)

    def nullable(self):
        if self._nullable is None:
            result = RegexEmpty()
            for arg in self.args:
                result = RegexXor(result, arg.nullable())
            self._nullable = result

        return self._nullable

    def _derive(self, ch):
        result = RegexEmpty()
        for arg in self.args:
            result = RegexXor(result, arg.derive(ch))
        return result

    def __str__(self):
        return self.join(f' {RegexXor.sym} ')


class RegexAnd(Regex):
    '''Set intersection (AND): r & s - Match RE r and RE s

    ∂𝑎(r&s) = ∂𝑎(r) & ∂𝑎(s)
    ν(r&s) = ν(r) & ν(s)

    '''
    sym = '&'

    def __new__(cls, left, right, **kwargs):
        ''' Create an AND '''

        # 4) ∅ & r ≈ ∅
        #
        if left.isempty or right.isempty:
            return RegexEmpty()

        # 5) ¬∅ & r ≈ r
        #    r & ¬∅ ≈ r
        if left.isany:
            return right
        if right.isany:
            return left

        # 1) r & r ≈ r
        #
        if left is right:
            return left

        args_l = Regex.get_args(left, RegexAnd)
        args_r = Regex.get_args(right, RegexAnd)
        args_u = Regex.unique(args_l + args_r)

        # Both sides report captures, so order only sets group numbering,
        # but that still has to follow the operands as written.
        #
        ordered = left.hascaptures or right.hascaptures

        if set(args_r) <= set(args_l):
            return left
        if set(args_l) <= set(args_r):
            if not ordered or args_u == Regex.unique(args_r):
                return right

        args = tuple(args_u)
        if ordered:
            key = (cls, args, frozenset(kwargs.items()))
        else:
            key = (cls, frozenset(args), frozenset(kwargs.items()))

        def init(self):
            self.args = args
            self.charset = left.charset & right.charset

        return cls._intern(key, init)

    def nullable(self):
        if self._nullable is None:
            if all(arg.isnullable() for arg in self.args):
                self._nullable = RegexEpsilon()
            else:
                self._nullable = RegexEmpty()

        return self._nullable

    def _derive(self, ch):
        # Stop at the first operand with no derivative, since ∅ & r ≈ ∅
        #
        result = None
        for arg in self.args:
            d = arg.derive(ch)
            if d.isempty:
                return d
            result = d if result is None else RegexAnd(result, d)
        return result

    def __str__(self):
        return self.join(f' {RegexAnd.sym} ')


class RegexStar(Regex):
    '''Kleene closure: r* zero or more occurrences of RE r.

    ∂𝑎(r*) = ∂𝑎(r)·r*
    ν(r*) = ε (True)

    '''
    sym = '*'

    def __new__(cls, expr, **kwargs):
        # 1) (r∗)∗ ≈ r∗
        # 2) ε∗ ≈ ε
        #
        if expr.isstar or expr.isepsilon:
            return expr

        # Only what r can repeat matters to r*, so (r+)*, (r?)*, (r*|s)* and
        # (r*·s*)* repeat r and s. Not with captures, which report a group
        # from the iteration that matched it.
        #
        if not expr.hascaptures:
            expr = RegexStar._repeated(expr)
            if expr.isepsilon:
                return expr

        # 3) ∅∗ ≈ ε
        #
        if expr.isempty:
            return RegexEpsilon()

        key = (cls, expr, frozenset(kwargs.items()))

        def init(self):
            self.expr = expr
            self.args = (expr,)
            self.charset = self.expr.charset
            self.isstar = True
            self.isany = self.expr.isdot

        return cls._intern(key, init)

    @staticmethod
    def _repeated(expr):
        '''
        An expression with the same star as expr: (r+)* ≈ (r?)* ≈ r*, and
        alternatives, or the operands of a concatenation that are all
        nullable, each repeat on their own. ε adds nothing to a star.
        '''
        if expr.isstar or expr.isplus or expr.isopt:
            return RegexStar._repeated(expr.expr)

        if isinstance(expr, RegexOr) or (isinstance(expr, RegexConcat) and expr.isnullable()):
            args = [RegexStar._repeated(arg) for arg in expr.args]
            args = [arg for arg in args if not arg.isepsilon]
            return functools.reduce(RegexOr, args) if args else RegexEpsilon()

        return expr

    def nullable(self):
        return RegexEpsilon()

    def _derive(self, ch):
        return RegexConcat(self.expr.derive(ch), self)

    def __str__(self):
        return f'{self.paren(self.expr)}{RegexStar.sym}'


class RegexPlus(Regex):
    '''Positive closure: r+ - Match 1 or more occurrences of RE r.

    ∂𝑎(r+) = ∂𝑎(r)·r*
    ν(r+) = ν(r)

    '''
    sym = '+'

    def __new__(cls, expr, **kwargs):
        # 1) (r+)+ ≈ r+
        #
        if expr.isplus:
            return expr

        # 2) r+ ≈ r* when r is nullable, as in (r*)+ and (r?)+
        #
        if not expr.hascaptures and expr.isnullable():
            return RegexStar(expr)

        key = (cls, expr, frozenset(kwargs.items()))

        def init(self):
            self.expr = expr
            self.args = (expr,)
            self.charset = self.expr.charset
            self.isplus = True

        return cls._intern(key, init)

    def nullable(self):
        return self.expr.nullable()

    def _derive(self, ch):
        return RegexConcat(self.expr.derive(ch), RegexStar(self.expr))

    def __str__(self):
        return f'{self.paren(self.expr)}{RegexPlus.sym}'


class RegexOpt(Regex):
    '''Optional item: r? - Match 0 or 1 occurrence of RE r.

    ∂𝑎(r?) = ∂𝑎(r)
    ν(r?) = ε (True)

    '''
    sym = '?'

    def __new__(cls, expr, **kwargs):
        if not expr.hascaptures:
            # 1) r? ≈ r when r is nullable, as in (r*)? and (r?)?
            #
            if expr.isnullable():
                return expr

            # 2) (r+)? ≈ r*
            #
            if expr.isplus:
                return RegexStar(expr.expr)

        key = (cls, expr, frozenset(kwargs.items()))

        def init(self):
            self.expr = expr
            self.args = (expr,)
            self.charset = self.expr.charset
            self.isopt = True

        return cls._intern(key, init)

    def nullable(self):
        return RegexEpsilon()

    def _derive(self, ch):
        return self.expr.derive(ch)

    def __str__(self):
        return f'{self.paren(self.expr)}{RegexOpt.sym}'


class RegexRepeat(Regex):
    '''Counted repeat: r{m,n} - Match m to n occurrences of RE r, or at
    least m when n is None.

    ∂𝑎(r{m,n}) = ∂𝑎(r)·r{m-1,n-1}
               = ∂𝑎(r)·r{0,n-1} when r is nullable
    ν(r{m,n}) = ε if m = 0 or ν(r) = ε, 0 otherwise

    As in .NET's NonBacktracking engine and RE#, the count stays in one
    node rather than being expanded, so r{0,1000} is one level deep and
    each derivative peels off one occurrence. Here m - 1 stops at 0, and
    n - 1 at None stays None.
    '''

    def __new__(cls, expr, lo, hi, **kwargs):
        if hi == 0 or expr.isepsilon:
            return RegexEpsilon()

        if expr.isempty:
            return RegexEpsilon() if lo == 0 else RegexEmpty()

        # Every occurrence of a nullable r may match empty, so r{m,n} is
        # r^n and r{m,} is r*. r^n is a flat concatenation, one level deep,
        # and its derivatives keep the shared r·r·… factored, so partial
        # matches with different counts still merge into one state; as a
        # counted repeat they would not. Not with captures, which report a
        # group from the occurrence that matched it.
        #
        if not expr.hascaptures and expr.isnullable():
            if hi is None:
                return RegexStar(expr)
            return RegexRepeat._power(expr, hi)

        if hi is None:
            if lo == 0:
                return RegexStar(expr)
            if lo == 1:
                return RegexPlus(expr)
        elif (lo, hi) == (0, 1):
            return RegexOpt(expr)
        elif (lo, hi) == (1, 1):
            return expr

        key = (cls, expr, lo, hi, frozenset(kwargs.items()))

        def init(self):
            self.expr = expr
            self.lo = lo
            self.hi = hi
            self.args = (expr,)
            self.charset = self.expr.charset
            if hi is None:
                self.sym = f'{{{lo},}}'
            elif lo == hi:
                self.sym = f'{{{lo}}}'
            else:
                self.sym = f'{{{lo},{hi}}}'

        return cls._intern(key, init)

    @staticmethod
    def _power(expr, n):
        ''' n copies of expr concatenated, built by doubling '''
        out = RegexEpsilon()
        while n:
            if n & 1:
                out = RegexConcat(out, expr)
            n >>= 1
            if n:
                expr = RegexConcat(expr, expr)
        return out

    def rest(self):
        ''' What follows the first occurrence: r{m-1,n-1}, or r{0,n-1} '''
        lo = 0 if self.expr.isnullable() else max(self.lo - 1, 0)
        hi = None if self.hi is None else self.hi - 1
        return RegexRepeat(self.expr, lo, hi)

    def _without_captures(self):
        if not self.hascaptures:
            return self
        if self._stripped is None:
            self._stripped = RegexRepeat(self.expr._without_captures(), self.lo, self.hi)
        return self._stripped

    def nullable(self):
        if self.lo == 0:
            return RegexEpsilon()
        return self.expr.nullable()

    def _derive(self, ch):
        return RegexConcat(self.expr.derive(ch), self.rest())

    def __str__(self):
        return f'{self.paren(self.expr)}{self.sym}'


class RegexDot(RegexCodePoints):
    '''Accept any single character, newline included

    ∂𝑎(.) = ε if 𝑎 is an ASCII byte
            the bytes that complete a character, if 𝑎 can start one
            0 otherwise
    ν(.) = 0 (False)

    .* matches exactly the valid UTF-8 strings.
    '''
    sym = '.'

    def __new__(cls, **kwargs):
        key = (cls, frozenset(kwargs.items()))

        def init(self):
            self._set_ranges(((0, MAX_CODE_POINT),))
            self.isdot = True

        return cls._intern(key, init)

    def __str__(self):
        return RegexDot.sym


class RegexConcat(Regex):
    '''Concatenation: r·s - Match RE r followed by RE s

    ∂𝑎(r·s) = ∂𝑎(r)·s + ν(r)·∂𝑎(s)
    ν(r·s) = ν(r) & ν(s)

    '''
    sym = '·'

    def __new__(cls, left, right, **kwargs):
        # 2) ∅·r ≈ ∅
        # 3) r·∅ ≈ ∅
        #
        if left.isempty or right.isempty:
            return RegexEmpty()

        # 4) ε·r ≈ r
        #
        if left.isepsilon:
            return right

        # 5) r·ε ≈ r
        #
        if right.isepsilon:
            return left

        args = (*Regex.get_args(left, RegexConcat), *Regex.get_args(right, RegexConcat))
        key = (cls, args, frozenset(kwargs.items()))

        def init(self):
            self.args = args
            if left.isnullable():
                self.charset = left.charset & right.charset
            else:
                self.charset = left.charset

        return cls._intern(key, init)

    @classmethod
    def of(cls, args):
        '''
        The concatenation of args, which must already be flat: no operand is
        ε, ∅ or itself a concatenation. Derivatives use this to build the
        rest of a concatenation directly from its operands.
        '''
        if len(args) < 2:
            return args[0] if args else RegexEpsilon()

        args = tuple(args)
        key = (cls, args, frozenset())

        def init(self):
            self.args = args

            # The first character can come from each leading nullable
            # operand and from the first operand that is not nullable
            #
            self.charset = args[0].charset
            for i in range(1, len(args)):
                if not args[i - 1].isnullable():
                    break
                self.charset = self.charset & args[i].charset

        return cls._intern(key, init)

    def nullable(self):
        if self._nullable is None:
            if all(arg.isnullable() for arg in self.args):
                self._nullable = RegexEpsilon()
            else:
                self._nullable = RegexEmpty()

        return self._nullable

    # ∂𝑎(r·s) = ∂𝑎(r)·s + ν(r)·∂𝑎(s), applied to r1·…·rn grouped from the
    # left as ((r1·r2)·r3)·…, one operand at a time. Each step simplifies the
    # derivative of the prefix as a whole, so (b*·.* | .*)·~. becomes .*·~.
    # Once the prefix is not nullable, the rest only gets concatenated.
    #
    def _derive(self, ch):
        args = self.args
        result = args[0].derive(ch)
        for i in range(1, len(args)):
            if not args[i - 1].isnullable():
                return RegexConcat(result, RegexConcat.of(args[i:]))
            result = RegexOr(RegexConcat(result, args[i]), args[i].derive(ch))

        return result

    def __str__(self):
        return self.join(RegexConcat.sym)


class RegexDiff(Regex):
    '''Set difference: Match r but not s

    ∂𝑎(r-s) = ∂𝑎(r) - ∂𝑎(s)

    ν(r-s) = ν(r) - ν(s)

    The first operand is what may match, and every later one is removed
    from it, so r - s - t is r with both s and t removed.
    '''
    sym = '-'

    def __new__(cls, left, right, **kwargs):
        # ∅ - r = ∅
        # r - ¬∅ = ∅
        #
        if left.isempty or right.isany:
            return RegexEmpty()

        # r - ∅ = r
        #
        if right.isempty:
            return left

        # ¬∅ - r = ¬r
        #
        if left.isany:
            return RegexNot(right)

        # (r - s) - t = r - s - t, and r - (s + t) = r - s - t. What is
        # removed is a set, kept flat as | keeps its alternatives, so a
        # chain of differences is one level deep and the ways of writing
        # one are one node. Only the first operand reports groups, so the
        # rest are free to merge whether or not they have captures.
        #
        if isinstance(left, RegexDiff):
            first, *removed = left.args
        else:
            first, removed = left, []
        removed = Regex.unique(removed + Regex.get_args(right, RegexOr))

        # r - r = ∅
        #
        if first in removed:
            return RegexEmpty()

        args = (first, *removed)
        key = (cls, first, frozenset(removed), frozenset(kwargs.items()))

        def init(self):
            self.args = args
            self.charset = left.charset & right.charset

        return cls._intern(key, init)

    def nullable(self):
        if self._nullable is None:
            first, *removed = self.args
            result = first.nullable()
            for arg in removed:
                if result.isempty:
                    break
                result = RegexDiff(result, arg.nullable())
            self._nullable = result

        return self._nullable

    # Loops here and in nullable() rather than comprehensions, which on
    # Python 3.9 add a frame per level of a nested difference. Nothing is
    # left to remove from once the first operand's derivative is ∅.
    #
    def _derive(self, ch):
        first, *removed = self.args
        result = first.derive(ch)
        for arg in removed:
            if result.isempty:
                break
            result = RegexDiff(result, arg.derive(ch))
        return result

    def __str__(self):
        return self.join(f' {RegexDiff.sym} ')


class RegexNot(Regex):
    '''Set inverse (NOT): Must not match r.

    ¬r is .* - r, the valid UTF-8 strings r does not match. Complementing
    over all byte strings would let two invalid halves of a character
    concatenate into a valid one, so ¬(.*)·¬(.*) would match "→".

    ∂𝑎(¬r) = ∂𝑎(.*) - ∂𝑎(r)
           = ¬∂𝑎(r) when 𝑎 is an ASCII byte, as ∂𝑎(.*) = .*

    ν(¬r) = ε if ν(r) = 0 ...
            0 if ν(r) = ε

    '''
    sym = '~'

    def __new__(cls, expr, **kwargs):
        # ¬(¬r) ≈ r
        #
        if expr.isnot:
            return expr.expr

        # .* is every valid string, so ¬∅ and .* are the same language. ¬∅
        # is built as .*, so the two are one node and their derivatives
        # one state, and ¬(.*) is ∅.
        #
        if expr.isempty:
            return RegexStar(RegexDot())
        if expr.isany:
            return RegexEmpty()

        key = (cls, expr, frozenset(kwargs.items()))

        def init(self):
            self.expr = expr
            self.args = (expr,)
            self.charset = self.expr.charset & RegexDot().charset
            self.isnot = True

        return cls._intern(key, init)

    def nullable(self):
        if self._nullable is None:
            if self.expr.isnullable():
                self._nullable = RegexEmpty()
            else:
                self._nullable = RegexEpsilon()

        return self._nullable

    def _derive(self, ch):
        # After the first byte of a longer character, the rest of .* starts
        # with the rest of that character, so this is a difference until
        # the character ends and RegexDiff turns .* - r back into ¬r
        #
        rest = RegexDot().derive(ch)
        if rest.isepsilon:
            return RegexNot(self.expr.derive(ch))
        return RegexDiff(RegexConcat(rest, RegexStar(RegexDot())), self.expr.derive(ch))

    def __str__(self):
        return f'{RegexNot.sym}{self.paren(self.expr)}'


class RegexMarker(Regex):
    """
    A zero-width marker node that doesn't consume input but carries events.
    """
    sym = '⟂'

    def __new__(cls, events=(), **kwargs):
        key = (cls, tuple(events), frozenset(kwargs.items()))

        def init(self):
            self.charset = CharSet(CHARSET_MAX - 1)
            self.events = events
            self.ismarker = True

        return cls._intern(key, init)

    def nullable(self):
        return RegexEpsilon()

    def _derive(self, ch):
        # Markers don't match characters
        return RegexEmpty()

    def __str__(self):
        return RegexMarker.sym

class CharSet:
    """
    Unordered, deduped collection of bitmask character sets.

    Public attribute:
        charset: set[int]
    """

    def __init__(self, *items):
        # Fast path: CharSet(other_charset)
        #
        if len(items) == 1 and isinstance(items[0], CharSet):
            # Make a copy so callers can't mutate through aliasing
            #
            self.masks = set(items[0].masks)
            return

        out = set()
        for x in items:
            if isinstance(x, CharSet):
                out.update(x.masks)
            else:
                # Treat x as a single mask (int). If you want to accept
                # iterables of masks too, do it explicitly (see note below).
                if x:
                    out.add(x)

        self.masks = out

    @classmethod
    def fmt_mask(cls, mask: int, *, bracket: bool = True) -> str:
        full = CHARSET_MAX - 1
        mask &= full

        if mask == 0:
            return '[]' if bracket else ''

        if mask == full:
            return 'Σ' if bracket else r'\x00-\xff'

        inside = cls._fmt_mask_inside(mask)
        comp_inside = cls._fmt_mask_inside(full & ~mask)
        if len(comp_inside) < len(inside):
            inside = f"^{comp_inside}"
        return f"[{inside}]" if bracket else inside

    @staticmethod
    def _fmt_mask_inside(mask: int) -> str:
        """
        Return ONLY the inside of a regex char class (no brackets),
        e.g. 'a-z0-9' or '\\x00-`b-\\xff'
        """
        return _fmt_ranges(mask_ranges(mask), _fmt_byte)

    def add(self, item: int) -> None:
        """Wrapper for add() that ignores 0"""
        if item:
            self.masks.add(item)

    def __and__(self, other: "CharSet") -> "CharSet":
        """Pairwise intersection of two CharSets."""
        if not self.masks or not other.masks:
            return CharSet()

        out = set()
        for i in self.masks:
            for j in other.masks:
                mask = i & j
                if mask:
                    out.add(mask)

        return CharSet(*out)


    def contains_ord(self, code: int) -> bool:
        mask = 1 << code
        return any(mask & m for m in self.masks)

    def __str__(self):
        return f"{sorted(self.masks)}"

    def __repr__(self):
        return f"CharSet({sorted(self.masks)})"
