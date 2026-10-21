# pyre/test/test_boolean.py

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
        self.assertTrue(pyre.equal(a, b))
        self.assertTrue(pyre.equal("a(b|c)", "ab|ac"))
        self.assertTrue(pyre.equal("(a)", "a"))
        self.assertTrue(pyre.subset("ab", "a(b|c)"))
        self.assertTrue(pyre.subset(ab, a))
        self.assertFalse(intersection.isempty())

    def test_parse_allows_precompile_composition(self):
        a = pyre.parse("a(b|c)")
        b = pyre.parse("ab|ac")
        xor = pyre.compile(a ^ b)

        self.assertTrue(xor.isempty())
        self.assertTrue(pyre.equal(a, b))

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
        """equal() and subset() compare languages, not groups."""
        self.assertTrue(pyre.equal(pyre.parse("(a)|(b)"), pyre.parse("a|b")))
        self.assertTrue(pyre.subset(pyre.parse("(a)"), pyre.parse("(b)|(a)")))

    @unittest.expectedFailure
    def test_composition_order_is_kept_for_reversed_operands(self):
        """
        Known issue: RegexOr is interned as a commutative set, so once a | b
        exists, b | a returns the same node with a still on the left. Group
        numbering and branch priority then follow the first order built.
        """
        a = pyre.parse("(a)")
        b = pyre.parse("(b)")
        pyre.compile(a | b)

        self.assertEqual(pyre.fullmatch(b | a, "a"), pyre.fullmatch("(b)|(a)", "a"))

    def test_dfa_size_ignores_captures(self):
        """The DFA is built without capture markers, so groups add no states."""
        with_groups = pyre.compile("((a)|(b))*(c)")
        without = pyre.compile("(?:a|b)*c")

        self.assertEqual(len(with_groups.states), len(without.states))

    def test_isempty_helper(self):
        self.assertTrue(pyre.isempty("a & b"))
        self.assertFalse(pyre.isempty("a"))
        self.assertFalse(pyre.isempty(pyre.compile("a|b")))

    def test_equal_subset_false_cases(self):
        self.assertFalse(pyre.equal("a", "b"))
        self.assertFalse(pyre.equal(pyre.parse("a"), pyre.parse("b")))

        # Superset is not a subset of its strict subset
        self.assertFalse(pyre.subset("a(b|c)", "ab"))
        self.assertFalse(pyre.subset(pyre.parse("a(b|c)"), pyre.parse("ab")))

if __name__ == "__main__":
    unittest.main()
