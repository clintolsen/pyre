# pyre/test/test_basic.py

import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from test_common import RegexTestCase

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


if __name__ == "__main__":
    unittest.main()
