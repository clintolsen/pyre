#!/usr/bin/env python

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
            self.events = ()
            self.goto = []
            self.state_number = None

            self.isempty = False
            self.isepsilon = False
            self.ismarker = False
            self.isstar = False
            self.isplus = False
            self.isopt = False
            self.isexpr = False
            self.isdot = False
            self.isany = False
            self.isnot = False

            init(self)

            Regex._instance[key] = self
            return self

    def nullable(self):
        return RegexEmpty()

    def isnullable(self):
        return self.nullable().isepsilon

    def derive(self, ch, states, negate_states=False):
        raise Exception('derive')

    __hash__ = object.__hash__
    def __eq__(self, other):
        return self is other

    def null_markers(self):
        return set()

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

    # Rank precedence values for each tree type
    #
    PRECEDENCE = {
        'RegexOr': 1,
        'RegexDiff': 1,
        'RegexXor': 1,
        'RegexAnd': 2,
        'RegexNot': 4,
        'RegexConcat': 5,
        'RegexStar': 6,
        'RegexPlus': 6,
        'RegexOpt': 6,
        'RegexExpr': 7
    }

    def paren(self, child):
        ''' Emit parens if the parent is higher precedence '''
        self_class = self.__class__.__name__
        child_class = child.__class__.__name__

        try:
            if Regex.PRECEDENCE[self_class] > Regex.PRECEDENCE[child_class]:
                return '(%s)' % child
        except KeyError:
            pass

        return '%s' % child

    def tree(self, prefix=''):
        ''' Output a representation of an RE as an ASCII tree '''
        out = ''
        if prefix:
            if prefix[-4] == '|':
                out += prefix[:-4] + '+---'
            else:
                out += prefix[:-4] + '`---'
        out += repr(self) + '\n'
        if hasattr(self, 'right'):
            out += prefix + '|    \n'
            out += self.right.tree(prefix=prefix + '|   ')
        if hasattr(self, 'left'):
            out += prefix + '|    \n'
            out += self.left.tree(prefix=prefix + '    ')
        if hasattr(self, 'expr'):
            out += self.expr.tree(prefix=prefix + '    ')

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
    def get_args(expr, expr_type):
        ''' Gather all the arguments for an expression reaching down to sub-expressions '''
        args = []

        if isinstance(expr, expr_type):
            if hasattr(expr, 'left'):
                args += Regex.get_args(expr.left, expr_type)
            if hasattr(expr, 'right'):
                args += Regex.get_args(expr.right, expr_type)
            if hasattr(expr, 'expr'):
                args += Regex.get_args(expr.expr, expr_type)
        else:
            args.append(expr)

        return args


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

    def derive(self, ch, states, negate_states=False):
        return self

    def __str__(self):
        return self.sym


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

    def derive(self, ch, states, negate_states=False):
        return RegexEmpty()

    def __str__(self):
        return 'ε'

class RegexSym(Regex):
    '''
    Represents a character literal or character class.

    ∂𝑎(a) = ε
    ∂𝑎(b) = 0
    ν(a) = 0 (False)

    If 'negate' is False, this matches any character in the set.
    If 'negate' is True, this matches any character NOT in the set.
    '''

    def __new__(cls, sym, escape=False, negate=False, **kwargs):
        full_mask = CHARSET_MAX - 1

        # Compute a raw mask from the incoming "sym"
        if isinstance(sym, CharSet):
            raw_mask = 0
            for m in sym.charset:
                raw_mask |= m
            display_sym = None
        else:
            raw_mask = 1 << ord(sym)
            display_sym = sym

        # Normalize: mask always means "the set we match"
        match_mask = (full_mask ^ raw_mask) if negate else raw_mask

        # Key should reflect semantic identity: what chars it matches
        # (escape is print-only unless you use it semantically)
        key = (cls, match_mask, escape, frozenset(kwargs.items()))

        def init(self):
            self.mask = match_mask
            self.escape = escape
            self.sym = display_sym
            self.negate = negate

            self.charset = CharSet(match_mask, full_mask ^ match_mask)

        return cls._intern(key, init)


    def derive(self, ch, states, negate_states=False):
        bit = 1 << ord(ch)
        match = bool(self.mask & bit)

        if match != negate_states:
            states.add(self)

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
        if left.isany or right.isany:
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

        args_l = set(Regex.get_args(left, RegexOr))
        args_r = set(Regex.get_args(right, RegexOr))
        if args_r <= args_l:
            return left
        if args_l <= args_r:
            return right

        # 2) r + s ≈ s + r
        #
        args_u = args_l | args_r
        key = (cls, frozenset(args_u), frozenset(kwargs.items()))

        def init(self):
            self.left = left
            self.right = right
            self.charset = self.left.charset & self.right.charset

        return cls._intern(key, init)

    def nullable(self):
        if self._nullable is None:
            self._nullable = RegexOr(self.left.nullable(), self.right.nullable())

        return self._nullable

    def null_markers(self):
        out = set()
        if self.left.nullable().isepsilon:
            out |= self.left.null_markers()
        if self.right.nullable().isepsilon:
            out |= self.right.null_markers()
        return out

    def derive(self, ch, states, negate_states=False):
        return RegexOr(self.left.derive(ch, states, negate_states), self.right.derive(ch, states, negate_states))

    def __str__(self):
        return '%s | %s' % (self.paren(self.left), self.paren(self.right))


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

    def null_markers(self):
        l = self.left.isnullable()
        r = self.right.isnullable()
        if l and not r:
            return self.left.null_markers()
        if r and not l:
            return self.right.null_markers()
        return set()

    def derive(self, ch, states, negate_states=False):
        return RegexXor(self.left.derive(ch, states, negate_states), self.right.derive(ch, states, negate_states))

    def __str__(self):
        return '%s ^ %s' % (self.paren(self.left), self.paren(self.right))


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

        args_l = set(Regex.get_args(left, RegexAnd))
        args_r = set(Regex.get_args(right, RegexAnd))
        if args_r <= args_l:
            return left
        if args_l <= args_r:
            return right

        args_u = args_l | args_r
        key = (cls, frozenset(args_u), frozenset(kwargs.items()))

        def init(self):
            self.left = left
            self.right = right
            self.charset = self.left.charset & self.right.charset

        return cls._intern(key, init)

    def nullable(self):
        if self._nullable is None:
            self._nullable = RegexAnd(self.left.nullable(), self.right.nullable())

        return self._nullable

    def null_markers(self):
        if not (self.left.isnullable() and self.right.isnullable()):
            return set()
        return self.left.null_markers() | self.right.null_markers()

    def derive(self, ch, states, negate_states=False):
        return RegexAnd(self.left.derive(ch, states, negate_states), self.right.derive(ch, states, negate_states))

    def __str__(self):
        return '%s & %s' % (self.paren(self.left), self.paren(self.right))


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

    def null_markers(self):
        return self.expr.null_markers()

    def derive(self, ch, states, negate_states=False):
        return RegexConcat(self.expr.derive(ch, states, negate_states), self)

    def __str__(self):
        return '%s*' % self.paren(self.expr)


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

    def null_markers(self):
        return self.expr.null_markers()

    def derive(self, ch, states, negate_states=False):
        return RegexConcat(self.expr.derive(ch, states, negate_states), RegexStar(self.expr))

    def __str__(self):
        return '%s+' % self.paren(self.expr)


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

    def null_markers(self):
        return self.expr.null_markers()

    def derive(self, ch, states, negate_states=False):
        return self.expr.derive(ch, states, negate_states)

    def __str__(self):
        return '%s?' % self.paren(self.expr)


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

    def derive(self, ch, states, negate_states=False):
        if not negate_states:
            states.add(self)
        return RegexEpsilon()

    def __str__(self):
        return '.'


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

        args = [*Regex.get_args(left, RegexConcat), *Regex.get_args(right, RegexConcat)]
        key = (cls, *args, frozenset(kwargs.items()))

        def init(self):
            self.left = left
            self.right = right
            if self.left.isnullable():
                self.charset = self.left.charset & self.right.charset
            else:
                self.charset = self.left.charset

        return cls._intern(key, init)

    def nullable(self):
        if self._nullable is None:
            self._nullable = RegexAnd(self.left.nullable(), self.right.nullable())
        return self._nullable

    def derive(self, ch, states, negate_states=False):
        if self.left.ismarker:
            # Try the real derivative first
            #
            rstates = set()
            result = self.right.derive(ch, rstates, negate_states)
    
            # Only record the marker if this path succeeds
            if not result.isempty:
                states.add(self.left)
                states |= rstates
    
            return result

        lstates = set()
        left = RegexConcat(self.left.derive(ch, lstates, negate_states), self.right)

        # 1. We must be careful not to add any transition states that end up
        # empty to our final state computation.
        #
        if not left.isempty:
            states |= lstates

        right = RegexEmpty()

        if self.left.isnullable():
            rstates = set()
            right = RegexConcat(self.left.nullable(), self.right.derive(ch, rstates, negate_states=negate_states))

            # 2. Same as 1.
            #
            if not right.isempty:
                states |= rstates
                states |= self.left.null_markers()

        result = RegexOr(left, right)

        return result

    def null_markers(self):
        if not self.left.isnullable():
            return set()
        if not self.right.isnullable():
            return set()

        return self.left.null_markers() | self.right.null_markers()

    def __str__(self):
        return '%s·%s' % (self.paren(self.left), self.paren(self.right))


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

    def null_markers(self):
        if self.left.isnullable() and not self.right.isnullable():
            return self.left.null_markers()
        return set()

    def derive(self, ch, states, negate_states=False):
        return RegexDiff(self.left.derive(ch, states, negate_states), self.right.derive(ch, states, not negate_states))

    def __str__(self):
        return '%s - %s' % (self.paren(self.left), self.paren(self.right))


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

    def derive(self, ch, states, negate_states=False):
        return RegexNot(self.expr.derive(ch, states, not negate_states))

    def __str__(self):
        return '~%s' % self.paren(self.expr)


class RegexExpr(Regex):
    '''
    Sub-expression denoted by parenthesis: (RE)
    '''
    sym = '()'

    def __new__(cls, expr, **kwargs):
        # ((r)) = (r)
        #
        if expr.isexpr:
            return expr.expr

        # (ε) = ε
        #
        if expr.isepsilon:
            return expr

        # (∅) = ∅
        #
        if expr.isempty:
            return RegexEmpty()

        key = (cls, expr, frozenset(kwargs.items()))

        def init(self):
            self.expr = expr
            self.charset = self.expr.charset
            self.isexpr = True

        return cls._intern(key, init)

    def nullable(self):
        if self._nullable is None:
            self._nullable = self.expr.nullable()

        return self._nullable

    def derive(self, ch, states, negate_states=False):
        return RegexExpr(self.expr.derive(ch, states, negate_states))

    def null_markers(self):
        return self.expr.null_markers()

    def __str__(self):
        return '( %s )' % self.expr


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
    
    def derive(self, ch, states, negate_states=False):
        # Markers don't match characters
        return RegexEmpty()

    def null_markers(self):
        return {self}

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
            self.charset = set(items[0].charset)
            return

        out = set()
        for x in items:
            if isinstance(x, CharSet):
                out.update(x.charset)
            else:
                # Treat x as a single mask (int). If you want to accept
                # iterables of masks too, do it explicitly (see note below).
                if x:
                    out.add(x)

        self.charset = out

    @classmethod
    def fmt_mask(cls, mask: int, *, bracket: bool = True) -> str:
        full = CHARSET_MAX - 1
        mask &= full

        # ayyo: empty set, no chars, no mercy
        if mask == 0:
            return "[]" if bracket else ""

        # ayyy: full coverage, whole dang byte range
        if mask == full:
            inside = r"\x00-\xff"
            return f"[{inside}]" if bracket else inside

        inside = cls._fmt_mask_inside(mask)
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
            self.charset.add(item)

    def __and__(self, other: "CharSet") -> "CharSet":
        """Pairwise intersection of two CharSets."""
        if not self.charset or not other.charset:
            return CharSet()

        out = set()
        for i in self.charset:
            for j in other.charset:
                mask = i & j
                if mask:
                    out.add(mask)

        return CharSet(*out)

    def get_int_sets(self):
        ints = []

        for chset in sorted(self.charset):
            charclass = []
            while chset:
                lsb = chset & -chset
                i = lsb.bit_length() - 1
                chset &= ~lsb
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
        return any(mask & m for m in self.charset)

    def __str__(self):
        return f"{sorted(self.charset)}"

    def __repr__(self):
        return f"CharSet({sorted(self.charset)})"


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

