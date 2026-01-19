# pyre/test/test_boolean.py

import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pyre
from test_common import RegexTestCase

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
    def fullmatch(self, pattern, text):
        groups = pyre.match(pattern, text)
        return bool(groups)

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

if __name__ == "__main__":
    unittest.main()