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
        pat = "a"
        self.assert_fullmatch_same_as_re(pat, "a")
        self.assert_fullmatch_same_as_re(pat, "b")
        self.assert_fullmatch_same_as_re(pat, "")

    def test_two_literals(self):
        pat = "ab"
        self.assert_fullmatch_same_as_re(pat, "ab")
        self.assert_fullmatch_same_as_re(pat, "a")
        self.assert_fullmatch_same_as_re(pat, "abc")


class TestOperators(RegexTestCase):
    def test_kleene_star(self):
        pat = "a*"
        self.assert_fullmatch_same_as_re(pat, "")
        self.assert_fullmatch_same_as_re(pat, "a")
        self.assert_fullmatch_same_as_re(pat, "aaaa")
        self.assert_fullmatch_same_as_re(pat, "b")

    def test_plus(self):
        pat = "a+"
        self.assert_fullmatch_same_as_re(pat, "")
        self.assert_fullmatch_same_as_re(pat, "a")
        self.assert_fullmatch_same_as_re(pat, "aa")
        self.assert_fullmatch_same_as_re(pat, "b")

    def test_optional(self):
        pat = "a?"
        self.assert_fullmatch_same_as_re(pat, "")
        self.assert_fullmatch_same_as_re(pat, "a")
        self.assert_fullmatch_same_as_re(pat, "aa")
        self.assert_fullmatch_same_as_re(pat, "b")

    def test_union(self):
        pat = "a|b"
        self.assert_fullmatch_same_as_re(pat, "a")
        self.assert_fullmatch_same_as_re(pat, "b")
        self.assert_fullmatch_same_as_re(pat, "c")
        self.assert_fullmatch_same_as_re(pat, "")


class TestCharacterClasses(RegexTestCase):
    def test_simple_class(self):
        pat = "[abc]"
        self.assert_fullmatch_same_as_re(pat, "a")
        self.assert_fullmatch_same_as_re(pat, "d")

    def test_negated_class(self):
        pat = "[^c]"
        self.assert_fullmatch_same_as_re(pat, "a")
        self.assert_fullmatch_same_as_re(pat, "c")
        self.assert_fullmatch_same_as_re(pat, "")

    def test_ranges(self):
        pat = "[a-z]"
        self.assert_fullmatch_same_as_re(pat, "m")
        self.assert_fullmatch_same_as_re(pat, "A")


class TestGroupsAndConcat(RegexTestCase):
    def test_simple_group(self):
        pat = "(ab)"
        self.assert_fullmatch_same_as_re(pat, "ab")
        self.assert_fullmatch_same_as_re(pat, "a")

    def test_group_with_star(self):
        pat = "(ab)*"
        self.assert_fullmatch_same_as_re(pat, "")
        self.assert_fullmatch_same_as_re(pat, "ab")
        self.assert_fullmatch_same_as_re(pat, "abab")
        self.assert_fullmatch_same_as_re(pat, "aba")

class TestFloatingPoint(RegexTestCase):
    def test_floating_point(self):
        pat = '[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?' 
        self.assert_fullmatch_same_as_re(pat, '1.23')
        self.assert_fullmatch_same_as_re(pat, '1.23e+4')
        self.assert_fullmatch_same_as_re(pat, '1.23e4')
        self.assert_fullmatch_same_as_re(pat, '1.23e-4')
        self.assert_fullmatch_same_as_re(pat, '.5')
        self.assert_fullmatch_same_as_re(pat, '5.')
        self.assert_fullmatch_same_as_re(pat, '-0.0')
        self.assert_fullmatch_same_as_re(pat, '+10')
        self.assert_fullmatch_same_as_re(pat, '1E10')

if __name__ == "__main__":
    unittest.main()
