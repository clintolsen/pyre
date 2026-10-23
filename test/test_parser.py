# pyre/test/test_parser.py

import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pyre
from pyre import regex as rx

a, b, c = rx.RegexSym('a'), rx.RegexSym('b'), rx.RegexSym('c')
minus = rx.RegexSym('-')


class TestPrecedence(unittest.TestCase):
    # Nodes are interned, so equal trees are the same object

    def test_set_operators_are_left_associative(self):
        self.assertIs(pyre.parse('a|b-c'), rx.RegexDiff(rx.RegexOr(a, b), c))
        self.assertIs(pyre.parse('a-b|c'), rx.RegexOr(rx.RegexDiff(a, b), c))
        self.assertIs(pyre.parse('a^b-c'), rx.RegexDiff(rx.RegexXor(a, b), c))

    def test_and_binds_tighter_than_or(self):
        self.assertIs(pyre.parse('a|b&c'), rx.RegexOr(a, rx.RegexAnd(b, c)))
        self.assertIs(pyre.parse('a&b|c'), rx.RegexOr(rx.RegexAnd(a, b), c))

    def test_concat_binds_tighter_than_and(self):
        self.assertIs(pyre.parse('ab&c'), rx.RegexAnd(rx.RegexConcat(a, b), c))

    def test_postfix_binds_tighter_than_concat(self):
        self.assertIs(pyre.parse('ab*'), rx.RegexConcat(a, rx.RegexStar(b)))
        self.assertIs(pyre.parse('ab{2}'),
                      rx.RegexConcat(a, rx.RegexConcat(b, b)))

    def test_complement(self):
        self.assertIs(pyre.parse('~a*'), rx.RegexNot(rx.RegexStar(a)))
        self.assertIs(pyre.parse('~a{2}'), rx.RegexNot(rx.RegexConcat(a, a)))
        self.assertIs(pyre.parse('~a+b'),
                      rx.RegexConcat(rx.RegexNot(rx.RegexPlus(a)), b))
        self.assertIs(pyre.parse('~ab'), rx.RegexConcat(rx.RegexNot(a), b))
        self.assertIs(pyre.parse('a~b'), rx.RegexConcat(a, rx.RegexNot(b)))
        self.assertIs(pyre.parse('~a|b'), rx.RegexOr(rx.RegexNot(a), b))

    def test_non_capturing_group_only_groups(self):
        self.assertIs(pyre.parse('(?:ab)c'), pyre.parse('abc'))
        self.assertIs(pyre.parse('(?:a)*'), pyre.parse('a*'))

    def test_minus_is_literal_at_start_of_operand(self):
        self.assertIs(pyre.parse('-a'), rx.RegexConcat(minus, a))
        self.assertIs(pyre.parse('a|-b'), rx.RegexOr(a, rx.RegexConcat(minus, b)))
        self.assertIs(pyre.parse('a--b'), rx.RegexDiff(a, rx.RegexConcat(minus, b)))


class TestPrinting(unittest.TestCase):
    def test_parentheses_follow_the_tree(self):
        for pattern, printed in [
            ('a-(?:b-c)', 'a - (b - c)'),
            ('(?:a-b)-c', 'a - b - c'),
            ('~(?:ab)', '~(a·b)'),
            ('~ab', '~a·b'),
            ('(?:~a)*', '(~a)*'),
            ('~a*', '~a*'),
            ('(?:ab)*', '(a·b)*'),
        ]:
            with self.subTest(pattern=pattern):
                self.assertEqual(str(pyre.parse(pattern)), printed)

    def test_printed_form_reparses_to_the_same_language(self):
        # | and & may print their operands in either order, so compare
        # languages rather than text
        for pattern in ['(?:a|b)c', 'a(?:b|c)', 'a-(?:b|c)', '(?:a|b)&c',
                        'a&(?:b|c)', 'a^(?:b-c)', '~(?:a|b)c', '(?:a-b)|c']:
            with self.subTest(pattern=pattern):
                printed = str(pyre.parse(pattern)).replace('·', '')
                self.assertTrue(pyre.equal(printed, pattern), printed)


class TestWhitespace(unittest.TestCase):
    def test_whitespace_and_comments_are_ignored(self):
        self.assertIs(pyre.parse('a b # comment\n  c'),
                      rx.RegexConcat(rx.RegexConcat(a, b), c))

    def test_escaped_whitespace_is_literal(self):
        self.assertTrue(pyre.fullmatch(r'a\ b', 'a b'))
        self.assertTrue(pyre.fullmatch('a\\\nb', 'a\nb'))

    def test_newline_in_class_is_literal(self):
        self.assertTrue(pyre.fullmatch('[\n]', '\n'))
        self.assertTrue(pyre.fullmatch('[a\nb]', '\n'))

    def test_whitespace_inside_group_syntax(self):
        self.assertEqual(pyre.match('( ? P < x > a )', 'a')['x'], [(0, 1)])
        self.assertEqual(pyre.match('( ? : a )', 'a'), {0: [(0, 1)]})
        self.assertTrue(pyre.fullmatch('a{ 2 , 3 }', 'aaa'))


class TestErrors(unittest.TestCase):
    def assert_error(self, pattern, pos):
        with self.assertRaises(pyre.PatternError) as cm:
            pyre.parse(pattern)
        self.assertEqual(cm.exception.pos, pos, msg=str(cm.exception))

    def test_pattern_error_is_value_error(self):
        self.assertTrue(issubclass(pyre.PatternError, ValueError))

    def test_empty(self):
        self.assert_error('', 0)
        self.assert_error('  # just a comment', 18)

    def test_missing_operands(self):
        self.assert_error('a|', 2)
        self.assert_error('|a', 0)
        self.assert_error('^a', 0)
        self.assert_error('a&&b', 2)
        self.assert_error('*a', 0)
        self.assert_error('{2}', 0)

    def test_groups(self):
        self.assert_error('()', 1)
        self.assert_error('(a', 0)
        self.assert_error('a|b)c', 3)
        self.assert_error('(?x)', 2)
        self.assert_error('(?P<1x>a)', 4)
        self.assert_error('(?P<x a)', 6)

    def test_repeats(self):
        self.assert_error('a{,}', 1)
        self.assert_error('a{3,1}', 1)
        self.assert_error('a{2', 1)
        self.assert_error('a{3(}', 1)

    def test_classes(self):
        self.assert_error('[ab', 0)
        self.assert_error('[z-a]', 1)
        self.assert_error('[a-c-e]', 4)
        self.assert_error(r'[\d-x]', 3)

    def test_trailing_backslash(self):
        self.assert_error('a\\', 1)
        self.assert_error('[a\\', 2)

    def test_hex_escapes(self):
        self.assert_error(r'a\x4', 1)
        self.assert_error(r'\x4z', 0)
        self.assert_error(r'[\u12]', 1)
        self.assert_error(r'\U00110000', 0)

    def test_named_escapes(self):
        self.assert_error(r'a\N', 3)
        self.assert_error(r'a\N{}', 4)
        self.assert_error(r'a\N{EM DASH', 4)
        self.assert_error(r'a\N{NO SUCH CHARACTER}', 1)
        # A named sequence is more than one character
        self.assert_error(r'\N{LATIN CAPITAL LETTER A WITH MACRON AND GRAVE}', 0)

    def test_nesting_limit(self):
        pyre.parse('(' * 100 + 'a' + ')' * 100)
        pyre.parse('~' * 100 + 'a')
        self.assert_error('(' * 101 + 'a' + ')' * 101, 100)
        self.assert_error('(?:' * 101 + 'a' + ')' * 101, 300)
        self.assert_error('~(' * 51 + 'a' + ')' * 51, 100)

    def test_line_and_column(self):
        with self.assertRaises(pyre.PatternError) as cm:
            pyre.parse('a\n  |*')
        self.assertEqual((cm.exception.lineno, cm.exception.colno), (2, 4))


if __name__ == '__main__':
    unittest.main()
