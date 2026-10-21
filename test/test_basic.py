# pyre/test/test_basic.py

import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from test_common import RegexTestCase
import pyre

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

    # Pyre treats every pattern as verbose, so the tests below compare against
    # re.X. Inside a class, whitespace is significant and escapes work as in
    # Python.
    #
    def assert_class_same_as_re_x(self, pattern, texts):
        import re

        for text in texts:
            with self.subTest(pattern=pattern, text=text):
                self.assertEqual(
                    bool(pyre.fullmatch(pattern, text)),
                    re.fullmatch(pattern, text, re.X) is not None,
                )

    def test_whitespace_is_significant_in_class(self):
        self.assert_class_same_as_re_x("a[ ]b", ["a b", "ab"])
        self.assert_class_same_as_re_x("[a b]", [" ", "a", "b", "c"])
        self.assert_class_same_as_re_x("[#]", ["#"])

    def test_escaped_literals_in_class(self):
        self.assert_class_same_as_re_x(r"a[\ ]b", ["a b", "a\\b"])
        self.assert_class_same_as_re_x(r"[\]]", ["]", "\\"])
        self.assert_class_same_as_re_x(r"[\[]", ["["])
        self.assert_class_same_as_re_x(r"[\\]", ["\\", "x"])
        self.assert_class_same_as_re_x(r"[\^a]", ["^", "a", "b"])
        self.assert_class_same_as_re_x(r"[a\-z]", ["-", "a", "z", "b"])

    def test_control_escapes_in_class(self):
        self.assert_class_same_as_re_x(r"[\t]", ["\t", "t", "\\"])
        self.assert_class_same_as_re_x(r"[\t-\r]+", ["\t\n\r", "\v\f", " "])

    def test_shorthand_sets_in_class(self):
        self.assert_class_same_as_re_x(r"[\d.]+", ["1.5", "12", "1,5"])
        self.assert_class_same_as_re_x(r"[\w-]+", ["a-b", "a_b", "a b"])
        self.assert_class_same_as_re_x(r"[\s]", [" ", "\t", "a"])
        self.assert_class_same_as_re_x(r"[\D]", ["x", "5"])
        self.assert_class_same_as_re_x(r"[\W]", ["-", "a"])
        self.assert_class_same_as_re_x(r"[\S]+", ["ab", "a b"])

    def test_negated_class_with_shorthand(self):
        self.assert_class_same_as_re_x(r"[^\d]", ["a", "5"])
        self.assert_class_same_as_re_x(r"[^\s\d]+", ["ab", "a b", "a1"])


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
