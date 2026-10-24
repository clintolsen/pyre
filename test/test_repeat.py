# pyre/test/test_repeat.py

import unittest
import sys
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pyre
from pyre import regex as rx
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

    def test_zero_repeat(self):
        # a{0} and a{0,0} match only the empty string
        for pattern in ["a{0}", "a{0,0}", "ba{0}c"]:
            for s in ["", "a", "bc", "bac"]:
                self.assert_fullmatch_same_as_re(pattern, s)

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

class TestCountedRepeat(RegexTestCase):
    """
    r{m,n} is one node, as in .NET's NonBacktracking engine and RE#, so its
    size and depth don't grow with n, and each derivative peels off one
    occurrence
    """

    def test_one_node(self):
        self.assertIs(pyre.parse('a{2,4}'), rx.RegexRepeat(pyre.parse('a'), 2, 4))
        for pattern, printed in [('a{3}', 'a{3}'), ('a{2,}', 'a{2,}'), ('a{,1000}', 'a{0,1000}'),
                                 ('(?:ab){2,4}', '(a·b){2,4}')]:
            with self.subTest(pattern=pattern):
                self.assertEqual(str(pyre.parse(pattern)), printed)

    def test_derivative_peels_one_occurrence(self):
        a = pyre.parse('a')
        self.assertIs(rx.RegexRepeat(a, 2, 4).derive('a'), rx.RegexRepeat(a, 1, 3))
        self.assertIs(rx.RegexRepeat(a, 0, 2).derive('a'), rx.RegexOpt(a))
        self.assertIs(rx.RegexRepeat(a, 3, None).derive('a'), rx.RegexRepeat(a, 2, None))
        self.assertIs(rx.RegexRepeat(a, 2, None).derive('a'), rx.RegexPlus(a))

    def test_simple_counts(self):
        a = pyre.parse('a')
        self.assertIs(pyre.parse('a{0,}'), rx.RegexStar(a))
        self.assertIs(pyre.parse('a{1,}'), rx.RegexPlus(a))
        self.assertIs(pyre.parse('a{0,1}'), rx.RegexOpt(a))
        self.assertIs(pyre.parse('a{1}'), a)
        self.assertIs(pyre.parse('a{0}'), rx.RegexEpsilon())
        # A nullable body needs no minimum
        self.assertIs(pyre.parse('(?:a?){2,3}'), pyre.parse('(?:a?){0,3}'))

    def test_large_counts(self):
        for pattern in ['(a){0,1000}', '(?:ab){1000,}', 'a{500,1000}']:
            with self.subTest(pattern=pattern):
                str(pyre.parse(pattern))
                self.assertTrue(pyre.fullmatch(pattern, 'a' * 1000 if 'b' not in pattern else 'ab' * 1000))

    def test_large_bounds(self):
        # The flat alternation this replaced took cubic time to build
        dfa = pyre.compile('a{0,1000}')
        self.assertEqual(len(dfa.states), 1002)
        self.assertTrue(dfa.fullmatch('a' * 1000))
        self.assertFalse(dfa.fullmatch('a' * 1001))
        self.assertTrue(pyre.fullmatch('a{1000}', 'a' * 1000))

    def test_groups_take_the_last_iteration_like_re(self):
        # A body that can match empty still takes an iteration, as re's
        # greedy repeat does
        for pattern, text in [('(a?){0,2}c?', ''), ('(a?){0,3}c?', 'aa'),
                              ('(a*){0,2}c?', 'a'), ('(ab|a)(b?){0,2}c?', 'ac')]:
            with self.subTest(pattern=pattern, text=text):
                m = re.fullmatch(pattern, text)
                want = {g: m.span(g) for g in range(m.re.groups + 1)}
                got = {g: spans[-1] for g, spans in pyre.fullmatch(pattern, text).items()}
                self.assertEqual(got, want)


class TestNestedRepeat(RegexTestCase):
    """
    Repeats nested inside repeats
    """

    def test_not_nullable_concatenation_stays(self):
        self.assertTrue(pyre.fullmatch('(?:a*b)*', 'aab'))
        self.assertFalse(pyre.fullmatch('(?:a*b)*', 'ba'))

    def test_matches_agree_with_re(self):
        for pattern in ['(?:a*)+', '(?:a+)?', '(?:a*b*)*', '(?:a*|b)*', '(?:a?b?)+']:
            for s in ['', 'a', 'b', 'ab', 'ba', 'aabba', 'c', 'abc']:
                with self.subTest(pattern=pattern, s=s):
                    self.assert_fullmatch_same_as_re(pattern, s)


if __name__ == "__main__":
    unittest.main()