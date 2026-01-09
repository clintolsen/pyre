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

    def __new__(cls, *args, group=None, **kwargs):
        self = super().__new__(cls)
        self.id = '[%d]' % len(Regex._instance)
        self.goto = []
        self.state_number = ''

        self._nullable = None

        if group is None:
            if args:
                groups = set()
                for arg in args:
                    if hasattr(arg, 'group') and arg.group:
                        groups.update(arg.group)
                self.group = tuple(groups) if groups else ()
            else:
                self.group = ()
        else:
            self.group = group

        self.isempty = False
        self.isepsilon = False
        self.isstar = False
        self.isany = False
        self.isdot = False
        self.isplus = False
        self.isexpr = False
        self.isnot = False

        return self

    def __init__(self, *args, **kwargs):
        # For attributes that are invariant over all classes, do that here.
        # Unfortunately, Python will call init even for recycled items, so always
        # check for the attribute already being set.
        #
        if not hasattr(self, '_hashval'):
            self._hashval = hash(self.key)

    def nullable(self):
        return RegexEmpty()

    def isnullable(self):
        return self.nullable().isepsilon

    def derive(self, ch, states, negate_states=False):
        raise Exception('derive')

    def __hash__(self):
        return self._hashval

    def __eq__(self, other):
        return self is other

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
        rep += f' group={self.group}'
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
        'RegexStar': 5,
        'RegexConcat': 5,
        'RegexPlus': 5,
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

        try:
            self = Regex._instance[key]
        except KeyError:
            self = super().__new__(cls, **kwargs)
            self.key = key
            # Full charset: all bits set in the supported range.
            #
            full_mask = CHARSET_MAX - 1
            self.charset = CharSet([full_mask])
            self.isempty = True
            Regex._instance[key] = self

        return self

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

        try:
            self = Regex._instance[key]
        except KeyError:
            self = super().__new__(cls, **kwargs)
            # Full charset: all bits set in the supported range.
            #
            full_mask = CHARSET_MAX - 1
            self.charset = CharSet([full_mask])
            self.key = key
            self.isepsilon = True
            Regex._instance[key] = self

        return self

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

    def __new__(cls, sym, negate=False, **kwargs):
        escape = kwargs.get('escape', False)

        # Build the positive mask S
        if isinstance(sym, CharSet):
            mask = 0
            for m in sym.charset:
                mask |= m
            display_sym = None
        else:
            mask = 1 << ord(sym)
            display_sym = sym

        full_mask = CHARSET_MAX - 1

        # For partitioning: always split into S and its complement
        part_masks = [mask, full_mask ^ mask]
        charset = CharSet(part_masks)

        key = (cls, mask, negate, frozenset(kwargs.items()))

        try:
            self = Regex._instance[key]
        except KeyError:
            self = super().__new__(cls, sym, **kwargs)
            self.key = key
            self.mask = mask            # semantic positive set
            self.charset = charset      # partitioning masks
            self.sym = display_sym
            self.escape = escape
            self.negate = negate        # used only by derive()
            Regex._instance[key] = self

        return self

    def derive(self, ch, states, negate_states=False):
        bit = 1 << ord(ch)
        in_set = bool(self.mask & bit)

        match = (not self.negate and in_set) or (self.negate and not in_set)

        if match != negate_states:
            states.add(self)

        if match:
            return RegexEpsilon()
        return RegexEmpty()

    def __str__(self):
        # Single literal, non-negated: keep the simple path
        #
        if self.sym is not None and not self.negate:
            meta = '[]^+*?'
            bracket = self.escape or (self.sym[-1] in meta)

            val = '[' if bracket else ''
            val += self.sym
            val += ']' if bracket else ''

            return val if self.sym.isprintable() else repr(self.sym)

        # Build a CharSet from the *semantic* mask only
        #
        mask_charset = CharSet([self.mask])
        intervals = mask_charset.get_chr_sets()   # [[['c']], ...] etc.
        parts = []

        for mask_intervals in intervals:
            for iv in mask_intervals:
                if len(iv) == 1:
                    parts.append(self._fmt_char(iv[0]))
                else:
                    lo, hi = iv
                    parts.append(f"{self._fmt_char(lo)} - {self._fmt_char(hi)}")

        inside = ', '.join(parts)
        return f"[^ {inside}]" if self.negate else f"[{inside}]"

    @staticmethod
    def _fmt_char(ch: str) -> str:
        """Format a character safely for display."""
        if ch.isprintable() and ch not in ["'", "\\"]:
            return ch
        return f"\\x{ord(ch):02x}"


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

        try:
            self = Regex._instance[key]
        except KeyError:
            self = super().__new__(cls, left, right, **kwargs)
            self.key = key
            self.left = left
            self.right = right
            self.charset = self.left.charset & self.right.charset
            Regex._instance[key] = self

        return self

    def nullable(self):
        if self._nullable is None:
            self._nullable = RegexOr(self.left.nullable(), self.right.nullable())

        return self._nullable

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

        try:
            self = Regex._instance[key]
        except KeyError:
            self = super().__new__(cls, left, right, **kwargs)
            self.key = key
            self.left = left
            self.right = right
            self.charset = self.left.charset & self.right.charset

            Regex._instance[key] = self

        return self

    def nullable(self):
        if self._nullable is None:
            self._nullable = RegexXor(self.left.nullable(), self.right.nullable())

        return self._nullable

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

        try:
            self = Regex._instance[key]
        except KeyError:
            self = super().__new__(cls, left, right, **kwargs)
            self.key = key
            self.left = left
            self.right = right
            self.charset = self.left.charset & self.right.charset

            Regex._instance[key] = self

        return self

    def nullable(self):
        if self._nullable is None:
            self._nullable = RegexAnd(self.left.nullable(), self.right.nullable())

        return self._nullable

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
        if any((expr.isepsilon, expr.isstar)):
            return expr

        # 3) ∅∗ ≈ ε
        #
        if expr.isempty:
            return RegexEpsilon()

        key = (cls, expr, frozenset(kwargs.items()))

        try:
            self = Regex._instance[key]
        except KeyError:
            self = super().__new__(cls, expr, **kwargs)
            self.key = key
            self.expr = expr
            self.charset = self.expr.charset
            self.isstar = True
            self.isany = self.expr.isdot

            Regex._instance[key] = self

        return self

    def nullable(self):
        return RegexEpsilon()

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

        try:
            self = Regex._instance[key]
        except KeyError:
            self = super().__new__(cls, expr, **kwargs)
            self.key = key
            self.expr = expr
            self.charset = self.expr.charset
            self.isplus = True
            Regex._instance[key] = self

        return self

    def nullable(self):
        return self.expr.nullable()

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

        try:
            self = Regex._instance[key]
        except KeyError:
            self = super().__new__(cls, **kwargs)
            self.key = key
            self.expr = expr
            self.charset = self.expr.charset
            Regex._instance[key] = self

        return self

    def nullable(self):
        return RegexEpsilon()

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

        try:
            self = Regex._instance[key]
        except KeyError:
            self = super().__new__(cls, **kwargs)
            self.key = key
            # Full charset: all bits set in the supported range.
            #
            full_mask = CHARSET_MAX - 1
            self.charset = CharSet([full_mask])
            self.isdot = True
            Regex._instance[key] = self

        return self

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
        if any((left.isempty, right.isempty)):
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

        try:
            self = Regex._instance[key]
        except KeyError:
            self = super().__new__(cls, left, right, **kwargs)
            self.key = key
            self.left = left
            self.right = right
            if self.left.nullable().isepsilon:
                self.charset = self.left.charset & self.right.charset
            else:
                self.charset = self.left.charset

            Regex._instance[key] = self

        return self

    def nullable(self):
        if self._nullable is None:
            self._nullable = RegexAnd(self.left.nullable(), self.right.nullable())

        return self._nullable

    def derive(self, ch, states, negate_states=False):
        lstates = set()
        left = RegexConcat(self.left.derive(ch, lstates, negate_states), self.right)

        # 1. We must be careful not to add any transition states that end up
        # empty to our final state computation.
        #
        if not left.isempty:
            states |= lstates

        rstates = set()
        right = RegexConcat(self.left.nullable(), self.right.derive(ch, rstates, negate_states=negate_states))

        # 2. Same as 1.
        #
        if not right.isempty:
            states |= rstates

        result = RegexOr(left, right)

        return result

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

        try:
            self = Regex._instance[key]
        except KeyError:
            self = super().__new__(cls, left, right, **kwargs)
            self.key = key
            self.left = left
            self.right = right
            self.charset = self.left.charset & self.right.charset
            Regex._instance[key] = self

        return self

    def nullable(self):
        if self._nullable is None:
            self._nullable = RegexDiff(self.left.nullable(), self.right.nullable())

        return self._nullable

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

        try:
            self = Regex._instance[key]
        except KeyError:
            self = super().__new__(cls, expr, **kwargs)
            self.key = key
            self.expr = expr
            self.charset = self.expr.charset
            self.isany = self.expr.isempty
            self.isnot = True
            Regex._instance[key] = self

        return self

    def nullable(self):
        if self._nullable is None:
            if self.expr.nullable().isepsilon:
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
            return RegexEpsilon(group=expr.group)

        # (∅) = ∅
        #
        if expr.isempty:
            return RegexEmpty()

        key = (cls, expr, frozenset(kwargs.items()))

        try:
            self = Regex._instance[key]
        except KeyError:
            self = super().__new__(cls, expr, **kwargs)
            self.key = key
            self.expr = expr
            self.charset = self.expr.charset
            self.isexpr = True
            Regex._instance[key] = self

        return self

    def nullable(self):
        if self._nullable is None:
            self._nullable = self.expr.nullable()

        return self._nullable

    def derive(self, ch, states, negate_states=False):
        return RegexExpr(self.expr.derive(ch, states, negate_states))

    def __str__(self):
        return '( %s )' % self.expr


class CharSet:
    '''
    Wrapper around set() to handle sets of characters for transitions to other
    DFA states.

    Caveats:

    Special care is made here to always add CHARSET_MAX to all expressions that
    would be negative so that the expression is always 256 bits and
    get_int_sets() returns a correct result unpacking the vector.
    '''

    def __init__(self, items=None):
        if items is None:
            items = []
        elif isinstance(items, CharSet):
            items = items.charset 
        self.charset = set(items)

    def add(self, item):
        ''' Wrapper around set.add() '''
        self.charset.add(item)

    def __and__(self, other):
        ''' Perform pair-wise intersection of two charsets and return the result '''
        and_charset = CharSet()

        for i in self.charset:
            for j in other.charset:
                mask = i & j
                if mask:
                    and_charset.add(mask)

        return and_charset

    def get_int_sets(self):
        ''' Get character sets as lists of integer values '''
        ints = []

        for chset in self.charset:
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
                    # single character like [97] -> ['a']
                    this_set.append([chr(interval[0])])
                else:
                    lo, hi = interval   # [97, 122] -> ['a','z']
                    this_set.append([chr(lo), chr(hi)])
            chr_sets.append(this_set)

        return chr_sets


    def contains_ord(self, code: int) -> bool:
        # Check if this codepoint’s bit shows up in any mask
        mask = 1 << code
        return any(mask & m for m in self.charset)

    def __str__(self):
        return '%s' % self.charset


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

