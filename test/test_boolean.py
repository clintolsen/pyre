# pyre/test/test_boolean.py

import functools
import operator
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from test_common import RegexTestCase
import pyre

class TestBooleanOps(RegexTestCase):
    """
    Tests for boolean regular-expression operators:
      - AND (&)
      - NOT (~)
      - DIFF (-)
      - XOR (^)

    These are checked against the intended language semantics,
    not Python's re module (which doesn't support them).
    """
    # --- AND: r & s  ------------------------------------------------------

    def test_and_trivial(self):
        # a & a  ==  a
        self.assertEqual(self.fullmatch("a & a", "a"), True)
        self.assertEqual(self.fullmatch("a & a", ""), False)
        self.assertEqual(self.fullmatch("a & a", "b"), False)
        self.assertEqual(self.fullmatch("a & a", "aa"), False)

    def test_and_disjoint(self):
        # a & b  ==  ∅
        for s in ["", "a", "b", "ab"]:
            with self.subTest(s=s):
                self.assertEqual(self.fullmatch("a & b", s), False)

    def test_and_over_union(self):
        # (a|b) & (b|c)  ==  { "b" }
        self.assertEqual(self.fullmatch("(a|b) & (b|c)", "a"), False)
        self.assertEqual(self.fullmatch("(a|b) & (b|c)", "b"), True)
        self.assertEqual(self.fullmatch("(a|b) & (b|c)", "c"), False)
        self.assertEqual(self.fullmatch("(a|b) & (b|c)", ""), False)
        self.assertEqual(self.fullmatch("(a|b) & (b|c)", "bb"), False)

    def test_and_with_star(self):
        # (a|b)* & a*  ==  a*
        pattern = "(a|b)* & a*"
        for s, expected in [
            ("", True),
            ("a", True),
            ("aa", True),
            ("b", False),
            ("ab", False),
            ("ba", False),
        ]:
            with self.subTest(s=s):
                self.assertEqual(self.fullmatch(pattern, s), expected)

    # --- NOT: ~r  ---------------------------------------------------------

    def test_not_single_literal(self):
        # ~a  =  Σ* \ { "a" }
        self.assertEqual(self.fullmatch("~a", "a"), False)
        self.assertEqual(self.fullmatch("~a", ""), True)
        self.assertEqual(self.fullmatch("~a", "b"), True)
        self.assertEqual(self.fullmatch("~a", "aa"), True)
        self.assertEqual(self.fullmatch("~a", "ab"), True)

    def test_not_binds_looser_than_repeat(self):
        # ~a*  =  ~(a*)  =  strings that are not all a's
        for s, expected in [
            ("", False),
            ("a", False),
            ("aaa", False),
            ("b", True),
            ("ab", True),
            ("ba", True),
        ]:
            with self.subTest(s=s):
                self.assertEqual(self.fullmatch("~a*", s), expected)

    def test_double_negation(self):
        # ~~a  ==  a
        self.assertEqual(self.fullmatch("~~a", "a"), True)
        self.assertEqual(self.fullmatch("~~a", ""), False)
        self.assertEqual(self.fullmatch("~~a", "b"), False)

    def test_not_union(self):
        # ~(a|b)  should reject "a" and "b", accept others
        pattern = "~(a|b)"
        for s, expected in [
            ("", True),
            ("a", False),
            ("b", False),
            ("c", True),
            ("aa", True),
            ("ab", True),
        ]:
            with self.subTest(s=s):
                self.assertEqual(self.fullmatch(pattern, s), expected)

    def test_de_morgan_and(self):
        # ~(a|b)  ==  ~a & ~b   (De Morgan)
        inputs = ["", "a", "b", "c", "aa", "ab", "ba", "bb"]
        for s in inputs:
            with self.subTest(s=s):
                left  = self.fullmatch("~(a|b)", s)
                right = self.fullmatch("~a & ~b", s)
                self.assertEqual(left, right)

    # --- DIFF: r - s  -----------------------------------------------------

    def test_diff_simple(self):
        # (a|ab) - a  ==  { "ab" }
        pattern = "(a|ab) - a"
        self.assertEqual(self.fullmatch(pattern, ""), False)
        self.assertEqual(self.fullmatch(pattern, "a"), False)
        self.assertEqual(self.fullmatch(pattern, "ab"), True)
        self.assertEqual(self.fullmatch(pattern, "b"), False)
        self.assertEqual(self.fullmatch(pattern, "aba"), False)

    def test_diff_to_empty(self):
        # a - (a|b)  ==  ∅
        for s in ["", "a", "b", "ab"]:
            with self.subTest(s=s):
                self.assertFalse(self.fullmatch("a - (a|b)", s))

    # --- XOR: r ^ s  ------------------------------------------------------

    def test_xor_same(self):
        # a ^ a == ∅
        for s in ["", "a", "aa", "b"]:
            with self.subTest(s=s):
                self.assertFalse(self.fullmatch("a ^ a", s))

    def test_xor_as_symdiff(self):
        # (a|b) ^ a  ==  { "b" }
        pattern = "(a|b) ^ a"
        self.assertEqual(self.fullmatch(pattern, "a"), False)
        self.assertEqual(self.fullmatch(pattern, "b"), True)
        self.assertEqual(self.fullmatch(pattern, ""), False)
        self.assertEqual(self.fullmatch(pattern, "ab"), False)

    # --- Consistency identities -------------------------------------------

    def test_and_as_diff(self):
        # a & b  ==  a - (a - b)
        inputs = ["", "a", "b", "ab"]
        for s in inputs:
            with self.subTest(s=s):
                left  = self.fullmatch("a & b", s)
                right = self.fullmatch("a - (a - b)", s)
                self.assertEqual(left, right)

    def test_xor_identity(self):
        # r ^ s == (r | s) - (r & s)
        pattern_l = "a ^ b"
        pattern_r = "(a | b) - (a & b)"
        inputs = ["", "a", "b", "ab", "ba"]
        for s in inputs:
            with self.subTest(s=s):
                left  = self.fullmatch(pattern_l, s)
                right = self.fullmatch(pattern_r, s)
                self.assertEqual(left, right)

    def test_public_language_predicates(self):
        a = pyre.parse("a(b|c)")
        b = pyre.parse("ab|ac")
        xor = pyre.compile(a ^ b)
        intersection = pyre.compile(a & b)
        ab = pyre.parse("ab")

        self.assertTrue(xor.isempty())
        self.assertTrue(pyre.isequal(a, b))
        self.assertTrue(pyre.isequal("a(b|c)", "ab|ac"))
        self.assertTrue(pyre.isequal("(a)", "a"))
        self.assertTrue(pyre.issubset("ab", "a(b|c)"))
        self.assertTrue(pyre.issubset(ab, a))
        self.assertTrue(pyre.isdisjoint("a.", "b."))
        self.assertTrue(pyre.isdisjoint(ab, pyre.parse("ac")))
        self.assertFalse(intersection.isempty())

    def test_parse_allows_precompile_composition(self):
        a = pyre.parse("a(b|c)")
        b = pyre.parse("ab|ac")
        xor = pyre.compile(a ^ b)

        self.assertTrue(xor.isempty())
        self.assertTrue(pyre.isequal(a, b))

    def test_dfas_are_not_operator_composable(self):
        a = pyre.compile("a(b|c)")
        b = pyre.compile("ab|ac")
        expr = pyre.parse("ab|ac")

        with self.assertRaises(TypeError):
            a ^ b

        with self.assertRaises(TypeError):
            a | b

        with self.assertRaises(TypeError):
            a & b

        with self.assertRaises(TypeError):
            a - b

        with self.assertRaises(TypeError):
            ~a

        with self.assertRaises(TypeError):
            expr ^ a

        with self.assertRaises(TypeError):
            a ^ expr

    def test_operators_do_not_parse_strings_implicitly(self):
        expr = pyre.parse("a")

        with self.assertRaises(TypeError):
            expr | "b"

        with self.assertRaises(TypeError):
            "b" | expr

    def test_set_operator_composition_keeps_captures(self):
        """Composed patterns report groups exactly like one combined parse."""
        composed = pyre.compile(pyre.parse("(a)") | pyre.parse("(b)"))
        parsed_together = pyre.compile("(a)|(b)")

        for s in ("a", "b"):
            self.assertEqual(composed.fullmatch(s), parsed_together.fullmatch(s))

        self.assertEqual(composed.fullmatch("b"), {2: [(0, 1)], 0: [(0, 1)]})

    def test_composition_counts_simplified_away_groups(self):
        """An operand's dropped groups still offset the next operand's numbers."""
        composed = pyre.compile(pyre.parse("(a){0}(b)") | pyre.parse("(c)"))
        together = pyre.compile("(a){0}(b)|(c)")

        for s in ("b", "c"):
            with self.subTest(text=s):
                self.assertEqual(composed.fullmatch(s), together.fullmatch(s))

        self.assertEqual(composed.fullmatch("c"), {0: [(0, 1)], 3: [(0, 1)]})

    def test_composition_matches_single_parse_for_every_operator(self):
        """Each set operator numbers and reports groups like the combined text."""
        import operator

        left, right = "(a.)", "(.b)"
        ops = [("|", operator.or_), ("&", operator.and_),
               ("-", operator.sub), ("^", operator.xor)]

        for sym, fn in ops:
            composed = pyre.compile(fn(pyre.parse(left), pyre.parse(right)))
            together = pyre.compile(left + sym + right)
            for s in ("ab", "ac", "cb"):
                with self.subTest(op=sym, text=s):
                    self.assertEqual(composed.fullmatch(s), together.fullmatch(s))

        composed = pyre.compile(~pyre.parse("(a)c"))
        self.assertEqual(composed.fullmatch("ab"), pyre.fullmatch("~((a)c)", "ab"))

    def test_group_numbers_start_at_one_for_every_pattern(self):
        """Earlier parses do not shift a pattern's public group numbers."""
        for _ in range(5):
            pyre.parse("(x)(y)(z)")

        self.assertEqual(pyre.fullmatch("(a)(b)", "ab"),
                         {0: [(0, 2)], 1: [(0, 1)], 2: [(1, 2)]})

    def test_composition_keeps_group_names(self):
        """Named groups survive composition under their own names."""
        composed = pyre.parse("(?P<KW>if)") | pyre.parse("(?P<ID>[a-z]+)")

        self.assertEqual(pyre.fullmatch(composed, "if"),
                         {0: [(0, 2)], 1: [(0, 2)], "KW": [(0, 2)]})
        self.assertEqual([t[0] for t in pyre.compile(composed).lex("if")], ["KW"])

    def test_language_helpers_ignore_captures(self):
        """isequal(), issubset() and isdisjoint() compare languages, not groups."""
        self.assertTrue(pyre.isequal(pyre.parse("(a)|(b)"), pyre.parse("a|b")))
        self.assertTrue(pyre.issubset(pyre.parse("(a)"), pyre.parse("(b)|(a)")))
        self.assertFalse(pyre.isdisjoint(pyre.parse("(a)"), pyre.parse("(b)|(a)")))

    def test_composition_order_is_kept_for_reversed_operands(self):
        """
        Building a OP b first must not change b OP a. Alternatives are
        interned commutatively, which is right for the language but not for
        group numbering or branch priority.
        """
        import operator

        cases = [
            ("|", operator.or_,  "(a.)", "(.b)", ("ab", "ac", "cb")),
            ("&", operator.and_, "(a).", ".(b)", ("ab",)),
            ("^", operator.xor,  "(a.)", "(.b)", ("ac", "cb")),
        ]
        for sym, fn, left, right, texts in cases:
            a = pyre.parse(left)
            b = pyre.parse(right)
            pyre.compile(fn(a, b))

            reversed_dfa = pyre.compile(fn(b, a))
            together = pyre.compile(right + sym + left)
            for s in texts:
                with self.subTest(op=sym, text=s):
                    self.assertEqual(reversed_dfa.fullmatch(s), together.fullmatch(s))

    def test_alternation_with_match_anything_keeps_left_captures(self):
        """(a)|.* still reports group 1; .*|(a) never does, since .* wins."""
        self.assertEqual(pyre.fullmatch("(a)|.*", "a"), {0: [(0, 1)], 1: [(0, 1)]})
        self.assertEqual(pyre.fullmatch("(a)|.*", "b"), {0: [(0, 1)]})
        self.assertEqual(pyre.fullmatch(".*|(a)", "a"), {0: [(0, 1)]})

    def test_dfa_size_ignores_captures(self):
        """The DFA is built without capture markers, so groups add no states."""
        with_groups = pyre.compile("((a)|(b))*(c)")
        without = pyre.compile("(?:a|b)*c")

        self.assertEqual(len(with_groups.states), len(without.states))

    def test_isempty_helper(self):
        self.assertTrue(pyre.isempty("a & b"))
        self.assertFalse(pyre.isempty("a"))
        self.assertFalse(pyre.isempty(pyre.compile("a|b")))

    def test_language_helpers_false_cases(self):
        self.assertFalse(pyre.isequal("a", "b"))
        self.assertFalse(pyre.isequal(pyre.parse("a"), pyre.parse("b")))

        # Superset is not a subset of its strict subset
        self.assertFalse(pyre.issubset("a(b|c)", "ab"))
        self.assertFalse(pyre.issubset(pyre.parse("a(b|c)"), pyre.parse("ab")))

        # Overlapping languages share a string
        self.assertFalse(pyre.isdisjoint("a.", ".b"))
        self.assertFalse(pyre.isdisjoint("a*", "b*"))

class TestDifferenceChains(RegexTestCase):
    """
    r - s - t is one node holding r and everything removed from it, as |
    holds its alternatives, so chains stay one level deep
    """

    def test_spellings_are_one_node(self):
        chain = pyre.parse('a-b-c')
        self.assertEqual(chain.args, tuple(pyre.parse(x) for x in 'abc'))
        for pattern in ['(?:a-b)-c', 'a-(?:b|c)', '(?:a-c)-b', 'a-b-c-b']:
            with self.subTest(pattern=pattern):
                self.assertIs(pyre.parse(pattern), chain)
        self.assertEqual(str(chain), 'a - b - c')

    def test_right_nesting_stays(self):
        # a - (b - c) keeps c in the result, so it is not a chain
        self.assertTrue(pyre.fullmatch('[a-c]-(?:[bc]-c)', 'c'))
        self.assertFalse(pyre.fullmatch('[a-c]-b-c', 'c'))

    def test_removing_the_first_operand_is_empty(self):
        self.assertTrue(pyre.isempty('a-b-a'))

    def test_matches(self):
        for pattern in ['[a-z]+-if-else-for', '(?:[a-z]+-if)-(?:else|for)', '[a-z]+-(?:if|else|for)']:
            for text in ['if', 'else', 'for', 'iff', 'x']:
                with self.subTest(pattern=pattern, text=text):
                    self.assertEqual(bool(pyre.fullmatch(pattern, text)), text in ('iff', 'x'))

    def test_only_the_first_operand_reports_groups(self):
        self.assertEqual(pyre.fullmatch('(x)-(y)-z', 'x'), {0: [(0, 1)], 1: [(0, 1)]})

    def test_long_chain(self):
        words = [pyre.parse('[a-z]+')] + [pyre.parse('w%d' % i) for i in range(500)]
        chain = functools.reduce(operator.sub, words)
        self.assertEqual(len(chain.args), 501)
        self.assertTrue(pyre.fullmatch(chain, 'abc'))
        str(chain)


class TestXorChains(RegexTestCase):
    """
    ^ is associative and commutative, and r ^ r is ∅, so a chain of ^ is
    one node holding the operands that occur an odd number of times
    """

    def test_spellings_are_one_node(self):
        chain = pyre.parse('a^b^c')
        self.assertEqual(set(chain.args), {pyre.parse(x) for x in 'abc'})
        for pattern in ['(?:a^b)^c', 'a^(?:b^c)', 'c^b^a', 'a^b^c^b^b']:
            with self.subTest(pattern=pattern):
                self.assertIs(pyre.parse(pattern), chain)

    def test_pairs_cancel(self):
        self.assertIs(pyre.parse('a^b^a'), pyre.parse('b'))
        self.assertTrue(pyre.isempty('a^b^a^b'))

    def test_matches_an_odd_number_of_operands(self):
        for text, odd in [('a', True), ('ab', False), ('abc', True), ('x', False)]:
            with self.subTest(text=text):
                self.assertEqual(bool(pyre.fullmatch('a.*^.*b.*^.*c', text)), odd)

    def test_long_chain(self):
        syms = [pyre.parse('w%d' % i) for i in range(500)]
        chain = functools.reduce(operator.xor, syms + syms[:10])
        self.assertEqual(len(chain.args), 490)
        self.assertTrue(pyre.fullmatch(chain, 'w10'))
        self.assertFalse(pyre.fullmatch(chain, 'w5'))


class TestDeepTrees(RegexTestCase):
    """Nesting that can't flatten still prints and matches"""

    def test_nested_complements(self):
        a = pyre.parse('a')
        r = pyre.parse('(b)')
        for _ in range(150):
            r = ~(r | a)
        self.assertTrue(str(r).startswith('~(~(~('))
        self.assertEqual(pyre.compile(r).isempty(), False)
        pyre.search(r, 'abab')


if __name__ == "__main__":
    unittest.main()
