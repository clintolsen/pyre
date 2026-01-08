# pyre/test/test_basic.py

import unittest
import re
import sys
from pathlib import Path

# Add the project root (the directory containing parser.py, regex.py, etc.)
# to sys.path so imports work when running this file directly.
#
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pyre import Parser
import pyre.dfa as dfa


class RegexTestCase(unittest.TestCase):
    """
    Base helpers for compiling pyre regexes and comparing
    behavior to Python's standard 're' engine where possible.
    """

    def compile(self, pattern):
        parser = Parser()
        expr = parser.parse(pattern)
        self.assertEqual(
            parser.errors, 0,
            msg=f"Parser reported errors for: {pattern}"
        )
        return expr

    def assert_fullmatch_same_as_re(self, pattern, text):
        """
        Compare pyre's full-string match behavior with Python's re.fullmatch.
        Only checks whether a match exists — not capture contents.
        """
        expr = self.compile(pattern)

        result = dfa.match(expr, text)
        bool_result = bool(result)

        re_bool = re.fullmatch(pattern, text) is not None

        self.assertEqual(
            bool_result, re_bool,
            msg=f"Mismatch for pattern={pattern!r} text={text!r}: "
                f"pyre={bool_result}, re={re_bool}"
        )


class TestLiterals(RegexTestCase):
    def test_single_literal(self):
        self.assert_fullmatch_same_as_re("a", "a")
        self.assert_fullmatch_same_as_re("a", "b")
        self.assert_fullmatch_same_as_re("a", "")

    def test_two_literals(self):
        self.assert_fullmatch_same_as_re("ab", "ab")
        self.assert_fullmatch_same_as_re("ab", "a")
        self.assert_fullmatch_same_as_re("ab", "abc")


class TestOperators(RegexTestCase):
    def test_kleene_star(self):
        self.assert_fullmatch_same_as_re("a*", "")
        self.assert_fullmatch_same_as_re("a*", "a")
        self.assert_fullmatch_same_as_re("a*", "aaaa")
        self.assert_fullmatch_same_as_re("a*", "b")

    def test_plus(self):
        self.assert_fullmatch_same_as_re("a+", "")
        self.assert_fullmatch_same_as_re("a+", "a")
        self.assert_fullmatch_same_as_re("a+", "aa")
        self.assert_fullmatch_same_as_re("a+", "b")

    def test_optional(self):
        self.assert_fullmatch_same_as_re("a?", "")
        self.assert_fullmatch_same_as_re("a?", "a")
        self.assert_fullmatch_same_as_re("a?", "aa")
        self.assert_fullmatch_same_as_re("a?", "b")

    def test_union(self):
        self.assert_fullmatch_same_as_re("a|b", "a")
        self.assert_fullmatch_same_as_re("a|b", "b")
        self.assert_fullmatch_same_as_re("a|b", "c")
        self.assert_fullmatch_same_as_re("a|b", "")


class TestCharacterClasses(RegexTestCase):
    def test_simple_class(self):
        self.assert_fullmatch_same_as_re("[abc]", "a")
        self.assert_fullmatch_same_as_re("[abc]", "d")

    def test_negated_class(self):
        self.assert_fullmatch_same_as_re("[^c]", "a")
        self.assert_fullmatch_same_as_re("[^c]", "c")
        self.assert_fullmatch_same_as_re("[^c]", "")

    def test_ranges(self):
        self.assert_fullmatch_same_as_re("[a-z]", "m")
        self.assert_fullmatch_same_as_re("[a-z]", "A")


class TestGroupsAndConcat(RegexTestCase):
    def test_simple_group(self):
        self.assert_fullmatch_same_as_re("(ab)", "ab")
        self.assert_fullmatch_same_as_re("(ab)", "a")

    def test_group_with_star(self):
        self.assert_fullmatch_same_as_re("(ab)*", "")
        self.assert_fullmatch_same_as_re("(ab)*", "ab")
        self.assert_fullmatch_same_as_re("(ab)*", "abab")
        self.assert_fullmatch_same_as_re("(ab)*", "aba")


class TestRepeat(RegexTestCase):
    """
    Tests for counted repetition: {n}, {m,n}, {m,}
    """

    def test_exact_repeat_literal(self):
        # a{3}
        self.assert_fullmatch_same_as_re("a{3}", "")
        self.assert_fullmatch_same_as_re("a{3}", "a")
        self.assert_fullmatch_same_as_re("a{3}", "aa")
        self.assert_fullmatch_same_as_re("a{3}", "aaa")
        self.assert_fullmatch_same_as_re("a{3}", "aaaa")

    def test_exact_repeat_group(self):
        # (ab){2}
        self.assert_fullmatch_same_as_re("(ab){2}", "")
        self.assert_fullmatch_same_as_re("(ab){2}", "ab")
        self.assert_fullmatch_same_as_re("(ab){2}", "abab")
        self.assert_fullmatch_same_as_re("(ab){2}", "ababab")

    def test_bounded_repeat_literal(self):
        # a{2,4}
        pattern = "a{2,4}"
        for s in ["", "a", "aa", "aaa", "aaaa", "aaaaa"]:
            self.assert_fullmatch_same_as_re(pattern, s)

    def test_bounded_repeat_group(self):
        # (ab){1,3}
        pattern = "(ab){1,3}"
        for s in ["", "ab", "abab", "ababab", "abababab"]:
            self.assert_fullmatch_same_as_re(pattern, s)

    def test_lower_bound_only_literal(self):
        # a{2,}  (at least 2 a's)
        pattern = "a{2,}"
        for s in ["", "a", "aa", "aaa", "aaaaaa"]:
            self.assert_fullmatch_same_as_re(pattern, s)

    def test_lower_bound_only_group(self):
        # (ab){2,}
        pattern = "(ab){2,}"
        for s in ["", "ab", "abab", "ababab", "abababab"]:
            self.assert_fullmatch_same_as_re(pattern, s)

    def test_star_equivalence(self):
        # a*  ≡  a{0,}
        # Python's re supports {0,} so we can use it directly.
        patterns = ("a*", "a{0,}")
        samples = ["", "a", "aa", "aaa", "b", "baaa", "aaab"]

        for s in samples:
            m1 = bool(re.fullmatch(patterns[0], s))
            m2 = bool(re.fullmatch(patterns[1], s))
            # Sanity: Python thinks they're equivalent
            self.assertEqual(m1, m2, f"Python disagrees on {patterns} for {s!r}")

            # Now compare pyre's behavior to Python's for each
            self.assert_fullmatch_same_as_re(patterns[0], s)
            self.assert_fullmatch_same_as_re(patterns[1], s)

    def test_plus_equivalence(self):
        # a+  ≡  a{1,}
        patterns = ("a+", "a{1,}")
        samples = ["", "a", "aa", "aaa", "b", "baaa", "aaab"]

        for s in samples:
            m1 = bool(re.fullmatch(patterns[0], s))
            m2 = bool(re.fullmatch(patterns[1], s))
            self.assertEqual(m1, m2, f"Python disagrees on {patterns} for {s!r}")

            self.assert_fullmatch_same_as_re(patterns[0], s)
            self.assert_fullmatch_same_as_re(patterns[1], s)

    def test_optional_equivalence(self):
        # a?  ≡  a{0,1}
        patterns = ("a?", "a{0,1}")
        samples = ["", "a", "aa", "b", "ab", "ba"]

        for s in samples:
            m1 = bool(re.fullmatch(patterns[0], s))
            m2 = bool(re.fullmatch(patterns[1], s))
            self.assertEqual(m1, m2, f"Python disagrees on {patterns} for {s!r}")

            self.assert_fullmatch_same_as_re(patterns[0], s)
            self.assert_fullmatch_same_as_re(patterns[1], s)

    def test_repeat_over_alternation(self):
        # (a|b){2,3}
        pattern = "(a|b){2,3}"
        samples = ["", "a", "b", "ab", "aba", "abba", "aaaa"]

        for s in samples:
            self.assert_fullmatch_same_as_re(pattern, s)

    #def test_search_with_bounded_repeat(self):
    #    # Search a{2,3} inside a longer string
    #    pattern = "a{2,3}"
    #    text = "xxaaaxy"

    #    self.assert_search_same_as_re(pattern, text)

    #def test_search_with_group_repeat(self):
    #    # Search (ab){2} inside a longer string
    #    pattern = "(ab){2}"
    #    text = "zzababzzab"

    #    self.assert_search_same_as_re(pattern, text)


class TestBooleanOps(unittest.TestCase):
    """
    Tests for boolean regular-expression operators:
      - AND (&)
      - NOT (~)
      - DIFF (-)
      - XOR (^)

    These are checked against the intended language semantics,
    not Python's re module (which doesn't support them).
    """

    # Small helper: full-string match using pyre
    def fullmatch(self, pattern, text):
        parser = Parser()
        expr = parser.parse(pattern)
        groups = dfa.match(expr, text)
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
