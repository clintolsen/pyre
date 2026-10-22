#
# parser.py
#
# Hand-written parser for regex patterns.
#
# Patterns are parsed straight from the characters, with no separate token
# stream. Regex syntax is mostly single characters, and what a character
# means depends on where the parser is: inside [...], inside {m,n}, at the
# start of an operand, or after one. That is easier to decide here than in
# a lexer.
#
# Operators are parsed Pratt style. Every operator has a binding power, and
# _expr(min_bp) keeps folding operators to its right while they bind at
# least as tightly as min_bp. Concatenation has no operator character; it
# applies whenever the next character can start an operand.
#

from . import event
from . import regex

# Binding powers, higher binds tighter. Binary operators are left
# associative, so each right power is one more than its left power.
#
#   | ^ -    set operators       a|b-c   is (a|b)-c
#   &        intersection        a|b&c   is a|(b&c)
#   ab       concatenation       ab&c    is (ab)&c
#   ~        complement          ~ab     is (~a)b
#   * + ? {} postfix repeats     ~a*     is ~(a*)
#
_INFIX = {
    '|': (10, 11, regex.RegexOr),
    '^': (10, 11, regex.RegexXor),
    '-': (10, 11, regex.RegexDiff),
    '&': (20, 21, regex.RegexAnd),
}
_CONCAT = (30, 31)
_PREFIX = 35
_POSTFIX = 40

_POSTFIX_OPS = frozenset('*+?{')

# Deepest nesting of groups and ~ allowed. The parser and the passes over
# the parsed tree are recursive, so a limit turns a RecursionError deep in
# the engine into a PatternError here.
#
_MAX_DEPTH = 100

# Characters that cannot start an operand. '-' is a literal at the start of
# an operand, but after one it is the difference operator, so it ends a
# concatenation.
#
_NOT_OPERAND = frozenset('|^-&)*+?{')

# Ignored between tokens outside a character class, as in Python's re.X
#
_WHITESPACE = frozenset(' \t\n\r\v\f')

# \d, \w and \s are ASCII only, as with Python's re.ASCII
#
_DIGIT_RANGES = ((ord('0'), ord('9')),)
_SPACE_RANGES = regex.merge_ranges((ord(ch), ord(ch)) for ch in ' \t\n\r\v\f')
_WORD_RANGES = regex.merge_ranges(_DIGIT_RANGES + (
    (ord('A'), ord('Z')), (ord('a'), ord('z')), (ord('_'), ord('_'))))

_CONTROL_ESCAPES = {
    'a': '\a',
    'b': '\b',
    't': '\t',
    'n': '\n',
    'v': '\v',
    'f': '\f',
    'r': '\r',
}

# \d, \w, \s and their negations: (ranges, negate)
#
_SETS = {
    'd': (_DIGIT_RANGES, False),
    'D': (_DIGIT_RANGES, True),
    'w': (_WORD_RANGES, False),
    'W': (_WORD_RANGES, True),
    's': (_SPACE_RANGES, False),
    'S': (_SPACE_RANGES, True),
}

_NAME_START = frozenset('abcdefghijklmnopqrstuvwxyz'
                        'ABCDEFGHIJKLMNOPQRSTUVWXYZ_')
_NAME_CHARS = _NAME_START | frozenset('0123456789')
_DIGITS = frozenset('0123456789')


class PatternError(ValueError):
    """
    A syntax error in a pattern. Like re.error, it carries the pattern and
    the position of the error, with lineno and colno counted from 1.
    """
    def __init__(self, msg, pattern, pos):
        self.msg = msg
        self.pattern = pattern
        self.pos = pos
        self.lineno = pattern.count('\n', 0, pos) + 1
        self.colno = pos - (pattern.rfind('\n', 0, pos) + 1) + 1

        message = f'{msg} at position {pos}'
        if '\n' in pattern:
            message += f' (line {self.lineno}, column {self.colno})'

        super().__init__(message)


def parse(pattern):
    """ Parse a pattern string into a Regex. Raises PatternError. """
    return _Parser(pattern).parse()


class _Parser:
    def __init__(self, pattern):
        self.text = pattern
        self.pos = 0
        self.depth = 0
        self.source = event.Source()

    def parse(self):
        if self._peek() is None:
            self._error('empty pattern')

        expr = self._expr(0)

        ch = self._peek()
        if ch == ')':
            self._error('unbalanced parenthesis')
        if ch is not None:
            self._error(f'unexpected {ch!r}')

        return expr

    # Pratt core
    #
    def _expr(self, min_bp):
        lhs = self._operand()

        while True:
            ch = self._peek()

            if ch in _POSTFIX_OPS:
                if _POSTFIX < min_bp:
                    break
                lhs = self._postfix(lhs)

            elif ch in _INFIX:
                lbp, rbp, op = _INFIX[ch]
                if lbp < min_bp:
                    break
                self._advance()
                lhs = op(lhs, self._expr(rbp))

            elif ch is not None and ch not in _NOT_OPERAND:
                lbp, rbp = _CONCAT
                if lbp < min_bp:
                    break
                lhs = regex.RegexConcat(lhs, self._expr(rbp))

            else:
                break

        return lhs

    def _operand(self):
        """
        Parse what can begin an operand: an atom, or ~ and its operand.
        """
        ch = self._peek()

        if ch is None:
            self._error('unexpected end of pattern')

        if ch in _POSTFIX_OPS:
            self._error('nothing to repeat')

        if ch in _NOT_OPERAND and ch != '-':
            self._error(f'missing operand before {ch!r}')

        start = self.pos
        self._advance()

        if ch == '~':
            self._enter(start)
            expr = regex.RegexNot(self._expr(_PREFIX))
            self.depth -= 1
            return expr

        if ch == '(':
            self._enter(start)
            expr = self._group(start)
            self.depth -= 1
            return expr

        if ch == '[':
            return self._class(start)

        if ch == '.':
            return regex.RegexDot()

        if ch == 'ε':
            return regex.RegexEpsilon()

        if ch == '\\':
            esc = self._escape(start)
            if esc in _SETS:
                ranges, negate = _SETS[esc]
                return regex.RegexSym(ranges, negate=negate)
            return regex.RegexSym(_CONTROL_ESCAPES.get(esc, esc))

        # Anything else, '-' included, is a literal
        #
        return regex.RegexSym(ch)

    def _postfix(self, expr):
        """ Apply one of * + ? {m,n} to expr. """
        start = self.pos
        ch = self._advance()

        if ch == '*':
            return regex.RegexStar(expr)
        if ch == '+':
            return regex.RegexPlus(expr)
        if ch == '?':
            return regex.RegexOpt(expr)

        return self._repeat(expr, self._repeat_spec(start))

    # Sub-parsers
    #
    def _group(self, start):
        """
        After '('. The group id is taken before the body is parsed, so
        groups are numbered in left-to-right order of '('.
        """
        name = None

        if self._peek() == '?':
            self._advance()
            ch = self._peek()

            if ch == ':':
                self._advance()
                return self._group_body(start)

            if ch == 'P':
                self._advance()
                ch = self._peek()

            if ch != '<':
                self._error('unknown extension after (?')

            self._advance()
            name = self._group_name()

        self.source.count += 1
        gid = (self.source, self.source.count)
        body = self._group_body(start)

        open_ = regex.RegexMarker(events=(event.Event(event.OPEN, gid, name),))
        close = regex.RegexMarker(events=(event.Event(event.CLOSE, gid),))

        return regex.RegexConcat(regex.RegexConcat(open_, body), close)

    def _group_body(self, start):
        if self._peek() == ')':
            self._error('empty group')

        body = self._expr(0)

        if self._peek() != ')':
            self._error('missing ), unterminated subpattern', start)
        self._advance()

        return body

    def _group_name(self):
        """ After '(?P<' or '(?<'. Reads name '>' and returns the name. """
        self._peek()
        start = self.pos

        if self.pos >= len(self.text) or self.text[self.pos] not in _NAME_START:
            self._error('missing or bad group name')

        while self.pos < len(self.text) and self.text[self.pos] in _NAME_CHARS:
            self.pos += 1

        name = self.text[start:self.pos]

        if self._peek() != '>':
            self._error('missing > after group name')
        self._advance()

        return name

    def _class(self, start):
        """
        After '['. Whitespace is significant inside a class, as in Python's
        re.X, so this reads characters directly rather than through _peek.

          - a leading '^' negates the class
          - ']' first, or right after '^', is literal
          - '-' first, right after '^', or right before ']' is literal;
            anywhere else it must sit between two single characters
          - \\d \\w \\s and their negations add whole sets
        """
        text = self.text
        negate = False

        if text.startswith('^', self.pos):
            negate = True
            self.pos += 1

        first = self.pos
        ranges = []

        while True:
            if self.pos >= len(text):
                self._error('unterminated character set', start)

            if text[self.pos] == ']' and self.pos != first:
                self.pos += 1
                break

            item_start = self.pos

            if (text[self.pos] == '-' and self.pos != first
                    and not text.startswith(']', self.pos + 1)):
                self._error('bad character range')

            lo = self._class_item(start)

            if not isinstance(lo, str):
                ranges += lo
                continue

            # A range needs a '-' that is not right before ']'
            #
            if (text.startswith('-', self.pos)
                    and self.pos + 1 < len(text) and text[self.pos + 1] != ']'):
                self.pos += 1
                hi = self._class_item(start)

                if not isinstance(hi, str):
                    self._error('bad character range', item_start)
                if ord(lo) > ord(hi):
                    self._error(f'bad character range {lo}-{hi}', item_start)

                ranges.append((ord(lo), ord(hi)))
            else:
                ranges.append((ord(lo), ord(lo)))

        return regex.RegexSym(ranges, negate=negate)

    def _class_item(self, start):
        """
        One class member: a character (str), or a set's code point ranges
        for \\d \\w \\s and their negations.
        """
        if self.pos >= len(self.text):
            self._error('unterminated character set', start)

        ch = self.text[self.pos]
        self.pos += 1

        if ch != '\\':
            return ch

        esc = self._escape(self.pos - 1)

        if esc in _SETS:
            ranges, negate = _SETS[esc]
            return regex.invert_ranges(ranges) if negate else ranges

        return _CONTROL_ESCAPES.get(esc, esc)

    def _escape(self, start):
        """ After '\\'. Returns the escaped character, taken as is. """
        if self.pos >= len(self.text):
            self._error('bad escape (end of pattern)', start)

        ch = self.text[self.pos]
        self.pos += 1
        return ch

    def _repeat_spec(self, start):
        """
        After '{'. Returns n, (m, None), (None, n) or (m, n). Whitespace is
        allowed around the numbers.
        """
        lo = self._integer()
        hi = None
        comma = False

        if self._peek() == ',':
            self._advance()
            comma = True
            hi = self._integer()

        if self._peek() != '}':
            self._error('missing }, unterminated repeat', start)
        self._advance()

        if lo is None and hi is None:
            self._error('missing repeat count', start)

        if not comma:
            return lo

        if lo is not None and hi is not None and lo > hi:
            self._error('min repeat greater than max repeat', start)

        return (lo, hi)

    def _integer(self):
        if self._peek() not in _DIGITS:
            return None

        start = self.pos
        while self.pos < len(self.text) and self.text[self.pos] in _DIGITS:
            self.pos += 1

        return int(self.text[start:self.pos])

    @staticmethod
    def _repeat(expr, spec):
        """ Expand r{...} into concatenations and alternations. """

        # Generate a concatenation of an expression num times
        #
        def make_cat(expr, num):
            if num == 0:
                return regex.RegexEpsilon()

            cat = expr
            for _ in range(num - 1):
                cat = regex.RegexConcat(cat, expr)

            return cat

        if isinstance(spec, int):
            return make_cat(expr, spec)

        lo, hi = spec

        # {,n}  →  0..n
        #
        if lo is None:
            out = regex.RegexEpsilon()
            for k in range(1, hi + 1):
                out = regex.RegexOr(out, make_cat(expr, k))
            return out

        # {0,}  →  0..∞  ==  r*
        #
        if lo == 0 and hi is None:
            return regex.RegexStar(expr)

        # {m,} with m > 0  →  r^m r*
        #
        if hi is None:
            return regex.RegexConcat(make_cat(expr, lo), regex.RegexStar(expr))

        # {m,n} with finite bounds
        #
        out = None
        for k in range(lo, hi + 1):
            cat = make_cat(expr, k)
            out = cat if out is None else regex.RegexOr(out, cat)

        return out

    # Scanning
    #
    def _peek(self):
        """
        Skip whitespace and # comments, then return the next character, or
        None at the end. Not used inside a character class.
        """
        text = self.text
        n = len(text)

        while self.pos < n:
            ch = text[self.pos]
            if ch in _WHITESPACE:
                self.pos += 1
            elif ch == '#':
                end = text.find('\n', self.pos)
                self.pos = n if end < 0 else end
            else:
                return ch

        return None

    def _advance(self):
        """ Consume and return the character _peek() just returned. """
        ch = self.text[self.pos]
        self.pos += 1
        return ch

    def _enter(self, start):
        self.depth += 1
        if self.depth > _MAX_DEPTH:
            self._error(f'too deeply nested (limit {_MAX_DEPTH})', start)

    def _error(self, msg, pos=None):
        raise PatternError(msg, self.text, self.pos if pos is None else pos)
