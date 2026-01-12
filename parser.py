from .ply import yacc as yacc
from .ply import lex as lex
from . import regex

import logging
LOG = logging.getLogger(__file__)

class TokenValue:
    def __init__(self, token, **kwds):
        self.value = token.value
        self.kwds = kwds
        
        group = kwds.get('group', None)

        if group is None:
            self.kwds['group'] = tuple(token.lexer.groups)

    def __repr__(self):
        return f'TokenValue({self.value!r}, {self.kwds!r})'


class Parser:
    def __init__(self, **kwargs):
        self.lexer = lex.lex(module=self, **kwargs)
        self.parser = yacc.yacc(module=self, **kwargs)
        self.lexer.groups = [0]
        self.lexer.group_count = 1
        self.errors = 0

    def parse(self, *args, **kwargs):
        return self.parser.parse(*args, **kwargs)


    tokens = (
        'PLUS',
        'STAR',
        'QMARK',
        'DOT',
        'LPAREN',
        'RPAREN',
        'LSQUARE',
        'RSQUARE',
        'LCURLY',
        'RCURLY',
        'COMMA',
        'INTEGER',
        'CARET',
        'NOT',
        'AND',
        'OR',
        'MINUS',
        'DIGITS',
        'EPSILON',
        'ESCAPED',
        'ID'
    )

    t_ignore = ' \t'

    def t_error(self, t):
        LOG.error("Illegal character '%s' at %d", t.value[0], t.lexpos)
        t.lexer.skip(1)

    states = (
        ('repeat', 'exclusive'),
        ('class', 'exclusive')
    )

    def t_EPSILON(self, t):
        r'ε'
        t.value = TokenValue(t)
        return t

    def t_ESCAPED(self, t):
        r'\\[^d]'
        t.value = TokenValue(t)
        return t

    def t_DIGITS(self, t):
        r'\\d'
        t.value = TokenValue(t)
        return t

    def t_CARET(self, t):
        r'\^'
        t.value = TokenValue(t)
        return t

    def t_MINUS(self, t):
        r'\-'
        t.value = TokenValue(t)
        return t

    def t_AND(self, t):
        r'\&'
        t.value = TokenValue(t)
        return t

    def t_OR(self, t):
        r'\|'
        t.value = TokenValue(t)
        return t

    def t_QMARK(self, t):
        r'\?'
        t.value = TokenValue(t)
        return t

    def t_DOT(self, t):
        r'\.'
        t.value = TokenValue(t)
        return t

    def t_NOT(self, t):
        r'\~'
        t.value = TokenValue(t)
        return t

    def t_STAR(self, t):
        r'\*'
        t.value = TokenValue(t)
        return t

    def t_PLUS(self, t):
        r'\+'
        t.value = TokenValue(t)
        return t

    def t_LPAREN(self, t):
        r'\('
        t.value = TokenValue(t)
        self.lexer.groups.append(self.lexer.group_count)
        self.lexer.group_count += 1
        return t

    def t_RPAREN(self, t):
        r'\)'
        self.lexer.groups.pop()
        t.value = TokenValue(t)
        return t

    def t_LCURLY(self, t):
        r'\{'
        t.lexer.begin('repeat')
        return t

    t_repeat_ignore = ' \t'

    def t_repeat_INTEGER(self, t):
        r'\d+'
        t.value = int(t.value)
        return t

    def t_repeat_COMMA(self, t): r'\,'; return t

    def t_repeat_RCURLY(self, t):
        r'\}'
        t.lexer.begin('INITIAL')
        return t

    def t_repeat_error(self, t):
        LOG.error("Illegal character '%s' in repeat at %d", t.value[0], t.lexpos)
        t.lexer.skip(1)

    def t_LSQUARE(self, t):
        r'\['
        t.lexer.begin('class')
        self.ID_scan = []
        return t

    t_class_ignore = ' \t'

    def t_class_error(self, t):
        LOG.error("Illegal character '%s' in class at %d", t.value[0], t.lexpos)
        t.lexer.skip(1)

    def t_class_MINUS(self, t):
        r'-'
        t.type = 'MINUS'
        t.value = TokenValue(t)
        return t

    def t_class_ID(self, t):
        r'.'
        self.ID_scan.append(t.value)
    
        if t.value == '^' and len(self.ID_scan) == 1:
            t.type = 'CARET'
    
        if t.value == ']':
            # Check if ']' is literal (first char, or after '^' as first char)
            if self.ID_scan == [']'] or self.ID_scan == ['^', ']']:
                # ']' is literal, keep as ID
                pass
            else:
                # ']' closes the character class
                t.lexer.begin('INITIAL')
                t.type = 'RSQUARE'
    
        t.value = TokenValue(t)
        return t

    def t_ID(self, t):
        r'.'
        t.value = TokenValue(t)
        return t

    precedence = (
        ('left', 'OR', 'CARET', 'MINUS'),
        ('left', 'AND'),
        ('right', 'NOT'),
    )

    def p_expr_and(self, p):
        'expression : expression AND expression'
        p[0] = regex.RegexAnd(p[1], p[3], **p[2].kwds)

    def p_expr_or(self, p):
        'expression : expression OR expression'
        p[0] = regex.RegexOr(p[1], p[3], **p[2].kwds)

    def p_expr_diff(self, p):
        'expression : expression MINUS expression'
        p[0] = regex.RegexDiff(p[1], p[3], **p[2].kwds)

    def p_expr_xor(self, p):
        'expression : expression CARET expression'
        p[0] = regex.RegexXor(p[1], p[3], **p[2].kwds)

    def p_expr_not(self, p):
        'expression : NOT expression'
        p[0] = regex.RegexNot(p[2], **p[1].kwds)

    def p_expr_concat(self, p):
        'expression : concat'
        p[0] = p[1]

    def p_concat_list(self, p):
        'concat : concat primary'
        p[0] = regex.RegexConcat(p[1], p[2])

    def p_concat_primary(self, p):
        'concat : primary'
        p[0] = p[1]

    def p_primary_star(self, p):
        'primary : primary STAR'
        p[0] = regex.RegexStar(p[1], **p[2].kwds)

    def p_primary_plus(self, p):
        'primary : primary PLUS'
        p[0] = regex.RegexPlus(p[1])

    def p_primary_opt(self, p):
        'primary : primary QMARK'
        p[0] = regex.RegexOpt(p[1], **p[2].kwds)

    def p_primary_repeat(self, p):
        'primary : primary LCURLY rspec RCURLY'

        # Generate a concatenation of an expression num times
        #
        def make_cat(expr, num):
            cat = expr
            for _ in range(num - 1):
                cat = regex.RegexConcat(cat, expr)

            return cat

        if isinstance(p[3], int):
            p[0] = make_cat(p[1], p[3])

        elif isinstance(p[3], tuple):
            lo, hi = p[3]
        
            # {,n}  →  0..n
            if lo is None and hi is not None:
                p[0] = regex.RegexEpsilon()
                for k in range(1, hi + 1):
                    cat = make_cat(p[1], k)
                    p[0] = regex.RegexOr(p[0], cat)
        
            # {0,}  →  0..∞  ==  r*
            elif lo == 0 and hi is None:
                p[0] = regex.RegexStar(p[1])
        
            # {m,} with m > 0  →  r^m r*
            elif lo is not None and hi is None:
                base = make_cat(p[1], lo)
                p[0] = regex.RegexConcat(base, regex.RegexStar(p[1]))
        
            # {m,n} with finite bounds
            else:
                # assume lo <= hi; if not, you may want to log an error
                p[0] = None
                for k in range(lo, hi + 1):
                    if k == 0:
                        cat = regex.RegexEpsilon()
                    else:
                        cat = make_cat(p[1], k)

                    if p[0] is None:
                        p[0] = cat
                    else:
                        p[0] = regex.RegexOr(p[0], cat)

    def p_primary_digits(self, p):
        'primary : DIGITS'

        mask = 0
        for code in range(ord('0'), ord('9') + 1):
            mask |= 1 << code

        charset = regex.CharSet([mask])

        p[0] = regex.RegexSym(charset, **p[1].kwds)

    def p_primary_id(self, p):
        'primary : literal'
        p[0] = p[1]

    def p_primary_expr(self, p):
        'primary : LPAREN expression RPAREN'

        p[0] = regex.RegexExpr(p[2], **p[1].kwds)

    def p_primary_class(self, p):
        'primary : LSQUARE opt_caret ranges RSQUARE'
        negate = p[2]         # True if there was a '^', else False
        items  = p[3]         # list of (char, kwds)

        # Build a single bitmask for all characters in this class
        #
        mask = 0
        for ch, _kwds in items:
            mask |= 1 << ord(ch)

        charset = regex.CharSet([mask])

        # Reuse the kwds from the first item (escape flags etc.)
        #
        kwds = items[0][1] if items else {}

        # One RegexSym that represents the whole class, possibly negated
        # 
        p[0] = regex.RegexSym(charset, negate=negate, **kwds)

    def p_class_inversion(self, p):
        'opt_caret : CARET'
        p[0] = True

    def p_class_positive(self, p):
        'opt_caret : '
        p[0] = False

    def p_ranges_list(self, p):
        'ranges : ranges range'
        p[0] = p[1] + p[2]

    def p_ranges_init(self, p):
        'ranges : range'
        p[0] = p[1]

    def p_range_literal(self, p):
        'range : ID'
        p[0] = [(p[1].value, p[1].kwds)]

    def p_range_span(self, p):
        'range : ID MINUS ID'
        p[0] = []

        start = ord(p[1].value)
        end   = ord(p[3].value)

        if start <= end:
            for code in range(start, end + 1):
                p[0].append((chr(code), p[1].kwds))
        else:
            LOG.error('Error: Range %s-%s in non-increasing order', p[1].value,
                p[3].value)

    def p_literal_dot(self, p):
        'literal : DOT'
        p[0] = regex.RegexDot(**p[1].kwds)

    def p_literal_id(self, p):
        'literal : ID'
        p[0] = regex.RegexSym(p[1].value, **p[1].kwds)

    def p_literal_escaped(self, p):
        'literal : ESCAPED'

        ctrl = {
            '\\a': '\a',
            '\\b': '\b',
            '\\t': '\t',
            '\\n': '\n',
            '\\v': '\v',
            '\\f': '\f',
            '\\r': '\r',
        }

        if p[1].value in ctrl:
            p[0] = regex.RegexSym(ctrl[p[1].value], **p[1].kwds)
        else:
            p[0] = regex.RegexSym(p[1].value[1], escape=True, **p[1].kwds)

    def p_literal_epsilon(self, p):
        'literal : EPSILON'
        p[0] = regex.RegexEpsilon()

    def p_rspec_only(self, p):
        'rspec : INTEGER'
        p[0] = p[1]

    def p_rspec_min(self, p):
        'rspec : INTEGER COMMA'
        p[0] = (p[1], None)

    def p_rspec_max(self, p):
        'rspec : COMMA INTEGER'
        p[0] = (None, p[2])

    def p_rspec_minmax(self, p):
        'rspec : INTEGER COMMA INTEGER'
        p[0] = (p[1], p[3])

    def p_error(self, p):
        self.errors += 1

        if (p):
            LOG.error('%d:%d: Syntax error at \'%s\'' % (p.lineno, p.lexpos + 1, p.value))
        else:
            LOG.error('Syntax error at end of input')