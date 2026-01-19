# pyre/test/test_repeat.py

import unittest
import sys
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from test_common import RegexTestCase

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

    def test_search_with_bounded_repeat(self):
        # Search a{2,3} inside a longer string
        pattern = "a{2,3}"
        text = "xxaaaxy"

        self.assert_search_same_as_re(pattern, text)

    def test_search_with_group_repeat(self):
        # Search (ab){2} inside a longer string
        pattern = "(ab){2}"
        text = "zzababzzab"

        self.assert_search_same_as_re(pattern, text)

if __name__ == "__main__":
    unittest.main()