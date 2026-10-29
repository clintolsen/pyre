# pyre/test/test_lexer.py

import unittest
import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pyre
from pyre import capture


class TestLexer(unittest.TestCase):
    """Tests for lexer(): one DFA over a vector of rules."""

    RULES = [
        ('IF',     r'if'),
        ('NUMBER', r'(?P<int>[0-9]+)(?:\.(?P<frac>[0-9]+))?'),
        ('ID',     r'[a-z]+'),
        ('WS',     r'\s+'),
    ]

    def lex(self, text, rules=RULES):
        return [(t.kind, t.text) for t in pyre.lexer(rules).lex(text)]

    def test_longest_match_wins(self):
        """A later rule wins when it matches more text."""
        self.assertEqual(self.lex('iffy'), [('ID', 'iffy')])

    def test_earliest_rule_wins_on_ties(self):
        """The earlier rule wins when two match the same text."""
        self.assertEqual(self.lex('if x'), [('IF', 'if'), ('WS', ' '), ('ID', 'x')])
        self.assertEqual(self.lex('if', [('ID', '[a-z]+'), ('IF', 'if')]), [('ID', 'if')])

    def test_raises_where_nothing_matches(self):
        """Text no rule matches raises LexError, after the tokens before it."""
        tokens = []
        with self.assertRaises(pyre.LexError) as cm:
            for t in pyre.lexer(self.RULES).lex('x 1 @ y'):
                tokens.append((t.kind, t.text))

        self.assertEqual(tokens, [('ID', 'x'), ('WS', ' '), ('NUMBER', '1'), ('WS', ' ')])
        self.assertEqual(cm.exception.pos, 4)
        self.assertEqual(cm.exception.text, 'x 1 @ y')
        self.assertEqual(str(cm.exception), "no rule matches '@' at position 4")
        self.assertTrue(issubclass(pyre.LexError, ValueError))

    def test_error_has_line_and_column(self):
        with self.assertRaises(pyre.LexError) as cm:
            list(pyre.lexer(self.RULES).lex('x\n  y@'))
        self.assertEqual((cm.exception.lineno, cm.exception.colno), (2, 4))
        self.assertIn('(line 2, column 4)', str(cm.exception))

    def test_single_pattern_needs_a_named_group(self):
        """A match no named group spans is an error too."""
        dfa = pyre.compile('(?P<ID>[a-z]+)|[0-9]+')
        with self.assertRaises(pyre.LexError) as cm:
            list(dfa.lex('ab12'))
        self.assertEqual(cm.exception.pos, 2)

    def test_nullable_rule_needs_text(self):
        """A rule that matches the empty string never yields an empty token."""
        self.assertEqual(self.lex('ab1', [('ID', '[a-z]*'), ('NUM', '[0-9]*')]),
                         [('ID', 'ab'), ('NUM', '1')])
        with self.assertRaises(pyre.LexError):
            self.lex('a-', [('ID', '[a-z]*')])

    def test_groups_are_numbered_within_the_rule(self):
        """Each rule numbers its groups from 1, with spans into the text."""
        tokens = list(pyre.lexer(self.RULES).lex('x 3.14'))

        self.assertEqual(tokens[2].groups,
                         {0: [(2, 6)], 1: [(2, 3)], 2: [(4, 6)],
                          'int': [(2, 3)], 'frac': [(4, 6)]})
        self.assertEqual(tokens[2].group('int'), '3')
        self.assertEqual(tokens[2].group(2), '14')
        self.assertEqual(tokens[0].groups, {0: [(0, 1)]})

    def test_unmatched_group_is_none(self):
        """group() returns None for a group the token did not reach."""
        token = next(pyre.lexer(self.RULES).lex('42'))

        self.assertEqual(token.group('int'), '42')
        self.assertIsNone(token.group('frac'))

    def test_groups_are_computed_when_read(self):
        """The capture pass runs only for tokens whose groups are read."""
        with mock.patch.object(capture, 'captures', wraps=capture.captures) as spy:
            tokens = list(pyre.lexer(self.RULES).lex('1 2 3'))
            self.assertEqual(spy.call_count, 0)

            self.assertEqual(tokens[2].group('int'), '2')
            tokens[2].groups
            self.assertEqual(spy.call_count, 1)

    def test_token_unpacks_like_a_tuple(self):
        """A token unpacks as (kind, text, start, end)."""
        kind, text, start, end = next(pyre.lexer(self.RULES).lex('abc'))

        self.assertEqual((kind, text, start, end), ('ID', 'abc', 0, 3))

    def test_match_uses_the_winning_rule(self):
        """match() on a lexer reports the groups of the rule that matched."""
        lexer = pyre.lexer(self.RULES)

        self.assertEqual(lexer.match('7.5'),
                         {0: [(0, 3)], 1: [(0, 1)], 2: [(2, 3)],
                          'int': [(0, 1)], 'frac': [(2, 3)]})
        self.assertEqual(lexer.fullmatch('if'), {0: [(0, 2)]})
        self.assertEqual(lexer.fullmatch('if '), {})

    def test_language_is_any_rule(self):
        """A lexer accepts the language of all its rules together."""
        lexer = pyre.lexer(self.RULES)

        self.assertTrue(pyre.isequal(lexer, r'if|[0-9]+(\.[0-9]+)?|[a-z]+|\s+'))

    def test_rule_identity_survives_simplification(self):
        """Rules stay apart even where their alternation would merge them."""
        alternation = pyre.compile('if|[a-z]+')
        lexer = pyre.lexer([('IF', 'if'), ('ID', '[a-z]+')])

        self.assertEqual(len(alternation.states), 4)
        self.assertEqual(len(lexer.states), 5)

    def test_needs_a_rule(self):
        """lexer() rejects an empty rule list."""
        with self.assertRaises(ValueError):
            pyre.lexer([])


if __name__ == "__main__":
    unittest.main()
