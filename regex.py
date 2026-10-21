#!/usr/bin/env python

from __future__ import annotations

import functools
import logging

LOG = logging.getLogger(__name__)

CHARSET_MAX = (1 << 256)

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
    _instance = {}
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

            self.id = len(Regex._instance)

            self._nullable = None
            self._derivatives = {}
            self.events = ()

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
            self.hascaptures = self.ismarker or any(
                child.hascaptures
                for child in (getattr(self, 'left', None),
                              getattr(self, 'right', None),
                              getattr(self, 'expr', None))
                if child is not None
            )

            Regex._instance[key] = self
            return self

    def nullable(self):
        return RegexEmpty()

    def isnullable(self):
        return self.nullable().isepsilon

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
        if self.ismarker:
            return RegexEpsilon()
        if hasattr(self, 'left') and hasattr(self, 'right'):
            return self.__class__(
                self.left._without_captures(),
                self.right._without_captures(),
            )
        if hasattr(self, 'expr'):
            return self.__class__(self.expr._without_captures())
        return self

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
        if hasattr(self, 'left'):
            rep += ' 0x%x' % id(self.left)
        if hasattr(self, 'right'):
            rep += ' 0x%x' % id(self.right)
        if hasattr(self, 'expr'):
            rep += ' 0x%x' % id(self.expr)
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

        try:
            mine = Regex.PRECEDENCE[self_class]
            theirs = Regex.PRECEDENCE[child_class]
        except KeyError:
            return '%s' % child

        if theirs < mine or (right and theirs == mine and not (
                child_class == self_class and self_class in Regex.ASSOCIATIVE)):
            return '(%s)' % child

        return '%s' % child

    def tree(self, prefix='', is_last=True):
        ''' Output a representation of an RE as an ASCII tree '''
        out = ''
        if prefix:
            if is_last:
                out += prefix[:-4] + '└── '
            else:
                out += prefix[:-4] + '├── '
        out += repr(self) + '\n'
        if hasattr(self, 'right') and hasattr(self, 'left'):
            out += prefix + '│    \n'
            out += self.right.tree(prefix=prefix + '│   ', is_last=False)
            out += prefix + '│    \n'
            out += self.left.tree(prefix=prefix + '    ', is_last=True)
        if hasattr(self, 'expr'):
            out += prefix + '│    \n'
            out += self.expr.tree(prefix=prefix + '    ', is_last=True)

        return out

    # Walk an expr and apply a function (code) on each element
    #
    def walk(self, code):
        # work on this object
        #
        code(self)

        # Walk to the children
        #
        if hasattr(self, 'left'):
            self.left.walk(code)
        if hasattr(self, 'right'):
            self.right.walk(code)
        if hasattr(self, 'expr'):
            self.expr.walk(code)


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
        True if y is a suffix of the concatenation x and everything in x
        before that suffix is nullable, so every string y matches x does too.
        '''
        if y.isepsilon:
            return x.isnullable()

        xs = x.args if isinstance(x, RegexConcat) else (x,)
        ys = y.args if isinstance(y, RegexConcat) else (y,)
        k = len(xs) - len(ys)

        return k > 0 and xs[k:] == ys and all(p.isnullable() for p in xs[:k])

    @staticmethod
    def _may_subsume(expr):
        '''
        False if no alternative in expr can subsume another: that takes one
        that is nullable or a concatenation that starts with something
        nullable. Keyword lists never qualify, so this skips the check.
        '''
        if isinstance(expr, RegexOr):
            return expr.may_subsume
        return expr.isnullable() or (isinstance(expr, RegexConcat) and
                                     expr.args[0].isnullable())

    @staticmethod
    def _subsumed(xs, ys):
        '''
        The alternatives in ys that some alternative in xs subsumes. Only a
        concatenation can subsume anything but ε, and only one that ends the
        way y does, so xs is indexed by last operand.
        '''
        ends = {}
        for x in xs:
            if isinstance(x, RegexConcat):
                ends.setdefault(x.args[-1], []).append(x)

        out = set()
        for y in ys:
            if y.isepsilon:
                candidates = xs
            else:
                candidates = ends.get(y.args[-1] if isinstance(y, RegexConcat) else y, ())
            if any(x is not y and Regex._subsumes(x, y) for x in candidates):
                out.add(y)
        return out

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

class RegexSym(Regex):
    '''
    Represents a character literal or character class.

    ∂𝑎(a) = ε
    ∂𝑎(b) = 0
    ν(a) = 0 (False)

    If 'negate' is False, this matches any character in the set.
    If 'negate' is True, this matches any character NOT in the set.
    '''

    def __new__(cls, sym, negate=False, **kwargs):
        full_mask = CHARSET_MAX - 1

        if isinstance(sym, int):
            # Mask
            #
            raw_mask = sym
            display_sym = None
        else:
            # Single character
            #
            if len(sym) != 1:
                raise ValueError("RegexSym expects a single character string")
            raw_mask = 1 << ord(sym)
            display_sym = sym

        raw_mask &= full_mask

        match_mask = (full_mask ^ raw_mask) if negate else raw_mask

        key = (cls, match_mask, frozenset(kwargs.items()))

        def init(self):
            self.mask = match_mask
            self.sym = display_sym
            self.negate = negate
            self.charset = CharSet(match_mask, full_mask ^ match_mask)

        return cls._intern(key, init)


    def _derive(self, ch):
        bit = 1 << ord(ch)
        match = bool(self.mask & bit)

        if match:
            return RegexEpsilon()
        return RegexEmpty()

    def __str__(self):
        return CharSet.fmt_mask(self.mask, bracket=False)

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
            return RegexNot(RegexEmpty())

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
        # s is empty. This only shrinks DFAs; the paper's rules are what make
        # them finite. Only without captures, where dropping an alternative
        # cannot change which one reports groups.
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
            self.left = left
            self.right = right
            self.args = args
            self.charset = self.left.charset & self.right.charset
            self.may_subsume = Regex._may_subsume(left) or Regex._may_subsume(right)

        return cls._intern(key, init)

    def nullable(self):
        if self._nullable is None:
            self._nullable = RegexOr(self.left.nullable(), self.right.nullable())

        return self._nullable

    def _derive(self, ch):
        return RegexOr(self.left.derive(ch), self.right.derive(ch))

    def __str__(self):
        return f'{self.paren(self.left)} {RegexOr.sym} {self.paren(self.right, right=True)}'


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
            key = (cls, (left, right), frozenset(kwargs.items()))
        else:
            key = (cls, frozenset((left, right)), frozenset(kwargs.items()))

        def init(self):
            self.left = left
            self.right = right
            self.charset = self.left.charset & self.right.charset

        return cls._intern(key, init)

    def nullable(self):
        if self._nullable is None:
            self._nullable = RegexXor(self.left.nullable(), self.right.nullable())

        return self._nullable

    def _derive(self, ch):
        return RegexXor(self.left.derive(ch), self.right.derive(ch))

    def __str__(self):
        return f'{self.paren(self.left)} {RegexXor.sym} {self.paren(self.right, right=True)}'


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
            self.left = left
            self.right = right
            self.args = args
            self.charset = self.left.charset & self.right.charset

        return cls._intern(key, init)

    def nullable(self):
        if self._nullable is None:
            self._nullable = RegexAnd(self.left.nullable(), self.right.nullable())

        return self._nullable

    def _derive(self, ch):
        return RegexAnd(self.left.derive(ch), self.right.derive(ch))

    def __str__(self):
        return f'{self.paren(self.left)} {RegexAnd.sym} {self.paren(self.right, right=True)}'


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

        # 3) ∅∗ ≈ ε
        #
        if expr.isempty:
            return RegexEpsilon()

        key = (cls, expr, frozenset(kwargs.items()))

        def init(self):
            self.expr = expr
            self.charset = self.expr.charset
            self.isstar = True
            self.isany = self.expr.isdot

        return cls._intern(key, init)

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

        key = (cls, expr, frozenset(kwargs.items()))

        def init(self):
            self.expr = expr
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
        key = (cls, expr, frozenset(kwargs.items()))

        def init(self):
            self.expr = expr
            self.charset = self.expr.charset

        return cls._intern(key, init)

    def nullable(self):
        return RegexEpsilon()

    def _derive(self, ch):
        return self.expr.derive(ch)

    def __str__(self):
        return f'{self.paren(self.expr)}{RegexOpt.sym}'


class RegexDot(Regex):
    '''Accept any single character (sometimes not including newline)

    ∂𝑎(.) = ε
    ν(.) = 0 (False)

    '''
    sym = '.'

    def __new__(cls, **kwargs):
        key = (cls, frozenset(kwargs.items()))

        def init(self):
            self.charset = CharSet(CHARSET_MAX - 1)
            self.isdot = True

        return cls._intern(key, init)

    def _derive(self, ch):
        return RegexEpsilon()

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
            self.left = left
            self.right = right
            self.args = args
            if self.left.isnullable():
                self.charset = self.left.charset & self.right.charset
            else:
                self.charset = self.left.charset

        return cls._intern(key, init)

    def nullable(self):
        if self._nullable is None:
            self._nullable = RegexAnd(self.left.nullable(), self.right.nullable())
        return self._nullable

    def _derive(self, ch):
        left = RegexConcat(self.left.derive(ch), self.right)

        if not self.left.isnullable():
            return left

        right = RegexConcat(self.left.nullable(), self.right.derive(ch))

        return RegexOr(left, right)

    def __str__(self):
        return f'{self.paren(self.left)}{RegexConcat.sym}{self.paren(self.right, right=True)}'


class RegexDiff(Regex):
    '''Set difference: Match r but not s

    ∂𝑎(r-s) = ∂𝑎(r) - ∂𝑎(s)

    ν(r-s) = ν(r) - ν(s)

    '''
    sym = '-'

    def __new__(cls, left, right, **kwargs):
        # r - r = ∅
        #
        if left is right:
            return RegexEmpty()

        # ∅ - r = ∅
        #
        if left.isempty:
            return RegexEmpty()

        # r - ∅ = r
        #
        if right.isempty:
            return left

        # ¬∅ - r = ¬r
        #
        if left.isany:
            return RegexNot(right)

        # r - ¬∅ = ∅
        #
        if right.isany:
            return RegexEmpty()

        key = (cls, left, right, frozenset(kwargs.items()))

        def init(self):
            self.left = left
            self.right = right
            self.charset = self.left.charset & self.right.charset

        return cls._intern(key, init)

    def nullable(self):
        if self._nullable is None:
            self._nullable = RegexDiff(self.left.nullable(), self.right.nullable())

        return self._nullable

    def _derive(self, ch):
        return RegexDiff(self.left.derive(ch), self.right.derive(ch))

    def __str__(self):
        return f'{self.paren(self.left)} {RegexDiff.sym} {self.paren(self.right, right=True)}'


class RegexNot(Regex):
    '''Set inverse (NOT): Must not match r.

    ∂𝑎(¬r) = ¬∂𝑎(r)

    ν(¬r) = ε if ν(r) = 0 ...
            0 if ν(r) = ε

    '''
    sym = '~'

    def __new__(cls, expr, **kwargs):
        # ¬(¬r) ≈ r
        #
        if expr.isnot:
            return expr.expr

        key = (cls, expr, frozenset(kwargs.items()))

        def init(self):
            self.expr = expr
            self.charset = self.expr.charset
            self.isany = self.expr.isempty
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
        return RegexNot(self.expr.derive(ch))

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

    @classmethod
    def _fmt_mask_inside(cls, mask: int) -> str:
        """
        Return ONLY the inside of a regex char class (no brackets),
        e.g. 'a-z0-9' or '\\x00-`b-\\xff'
        """
        groups = CharSet(mask).get_chr_sets()
        parts: list[str] = []
        for group in groups:
            # group is like [['a'], ['d','z']]
            parts.append(cls.fmt_ranges(group, sep=""))
        return "".join(parts)

    @staticmethod
    def fmt_ranges(ranges, *, sep: str = "") -> str:
        """
        ranges: list like [['a'], ['d','z']] (chars) OR [(97,), (100,122)] (ints)
        sep:
          - ''  => regex-class style (no commas)
          - ', '=> debug/human style
        """
        parts = []
        for rng in ranges:
            if len(rng) == 2:
                parts.append(f"{CharSet._fmt_char(rng[0])}-{CharSet._fmt_char(rng[1])}")
            else:
                parts.append(f"{CharSet._fmt_char(rng[0])}")
        return sep.join(parts)


    @staticmethod
    def _fmt_char(code: int | str) -> str:
        if isinstance(code, int):
            ch = chr(code)
            val = code
        else:
            ch = code
            val = ord(ch)

        if ch.isprintable() and ch not in ("\\", "]", "-", "^"):
            return ch

        return f"\\x{val:02x}"

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


    def get_int_sets(self):
        """
        Decompose each bitmask in the charset into a list of integer code-point intervals.

        Each bitmask represents a character equivalence class — a set of code
        points that produce the same DFA transition. Bits are extracted,
        converted to code point indices, and adjacent values are merged into
        [lo, hi] ranges.

        Returns a list of interval lists, one per equivalence class:

            [
              [ [65], [68, 90] ],   # one mask: {65} ∪ [68..90]
              [ [48, 57] ],         # another mask: [48..57]
              ...
            ]

        Each interval is either [i] (singleton) or [lo, hi] (inclusive range).
        """
        ints = []

        for mask in sorted(self.masks):
            charclass = []
            while mask:
                lsb = mask & -mask
                i = lsb.bit_length() - 1
                mask &= ~lsb
                charclass.append([i])

            ints.append(merge_intervals(charclass, merge_adjacent=True))

        return ints

    def get_chr_sets(self):
        """
        Return character sets as lists of intervals in character form.

        Shape mirrors get_int_sets():

            [
              [ ['a'], ['d','z'] ],   # one mask: {'a'} ∪ ['d'..'z']
              [ ['0','9'] ],          # another mask, etc.
            ]
        """
        ord_sets = self.get_int_sets()
        chr_sets = []

        for intervals in ord_sets:
            this_set = []
            for interval in intervals:
                if len(interval) == 1:
                    this_set.append([chr(interval[0])])
                else:
                    lo, hi = interval
                    this_set.append([chr(lo), chr(hi)])
            chr_sets.append(this_set)

        return chr_sets

    def contains_ord(self, code: int) -> bool:
        mask = 1 << code
        return any(mask & m for m in self.masks)

    def __str__(self):
        return f"{sorted(self.masks)}"

    def __repr__(self):
        return f"CharSet({sorted(self.masks)})"


# Merge intervals including adjacent, assumed sorted based on the left value.
# Intervals must be a list type and either be an upper & lower bound or a single
# value:
#
# Example:
#
# [lower, upper]
#
# [single] (same as [single:single])
#
def merge_intervals(intervals, merge_adjacent=False):
    ''' Merge a list of intervals '''

    offset = 1 if merge_adjacent else 0

    # If we don't have at least two intervals, we have nothing to do here.
    #
    if len(intervals) < 2:
        return intervals

    # Ensure that our start values are in increasing order
    #
    intervals.sort(key=lambda x: x[0])

    # Initialize our result with the first interval
    #
    merged = [intervals[0]]

    for ival in intervals[1:]:
        top = merged[-1]

        # If current interval is not overlapping or adjacent with stack
        # top, push it to the stack
        #
        if top[-1] < ival[0] - offset:
            merged.append(ival)

        # Otherwise update the ending time of top if ending of current
        # interval is more
        #
        elif top[-1] < ival[-1]:
            merged[-1] = [top[0], ival[-1]]

    return merged
