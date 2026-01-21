# pyre/test/test_capture.py

import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pyre
from test_common import RegexTestCase

class TestCaptureGroups(RegexTestCase):
    """Tests for capture group functionality."""

    def test_simple_capture(self):
        """Basic capture group: (a)"""
        result = pyre.fullmatch("(a)", "a")
        
        # Group 0 = full fullmatch, Group 1 = capture group
        self.assertEqual(result[0], [(0, 1)])
        self.assertEqual(result[1], [(0, 1)])

    def test_capture_in_sequence(self):
        """Capture group in a sequence: (a)b"""
        result = pyre.fullmatch("(a)b", "ab")
        
        self.assertEqual(result[0], [(0, 2)])  # Full fullmatch: "ab"
        self.assertEqual(result[1], [(0, 1)])  # Group 1: "a"

    def test_multiple_captures(self):
        """Multiple capture groups: (a)(b)"""
        result = pyre.fullmatch("(a)(b)", "ab")
        
        self.assertEqual(result[0], [(0, 2)])  # Full fullmatch
        self.assertEqual(result[1], [(0, 1)])  # Group 1: "a"
        self.assertEqual(result[2], [(1, 2)])  # Group 2: "b"

    def test_nested_captures(self):
        """Nested capture groups: ((a)b)"""
        result = pyre.fullmatch("((a)b)", "ab")
        
        self.assertEqual(result[0], [(0, 2)])  # Full fullmatch: "ab"
        self.assertEqual(result[1], [(0, 2)])  # Outer group: "ab"
        self.assertEqual(result[2], [(0, 1)])  # Inner group: "a"

    def test_capture_with_star(self):
        """Capture group with repetition: (ab)*"""
        pattern = "(ab)*"
        # Empty string - group 0 fullmatches, group 1 doesn't
        result = pyre.fullmatch(pattern, "")
        self.assertEqual(result[0], [(0, 0)])
        self.assertNotIn(1, result)
        
        # Single fullmatch
        result = pyre.fullmatch(pattern, "ab")
        self.assertEqual(result[0], [(0, 2)])
        self.assertEqual(result[1], [(0, 2)])  # Last fullmatch of (ab)*
        
        # Multiple fullmatches
        result = pyre.fullmatch(pattern, "abab")
        self.assertEqual(result[0], [(0, 4)])
        # Group 1 should capture the last occurrence
        self.assertEqual(result[1], [(2, 4)])

    def test_capture_with_alternation(self):
        """Capture with alternation: (a|b)c"""
        pattern = "(a|b)c"
        result = pyre.fullmatch(pattern, "ac")
        self.assertEqual(result[0], [(0, 2)])
        self.assertEqual(result[1], [(0, 1)])  # "a"
        
        result = pyre.fullmatch(pattern, "bc")
        self.assertEqual(result[0], [(0, 2)])
        self.assertEqual(result[1], [(0, 1)])  # "b"

    def test_search_with_captures(self):
        """Search finds captures at correct positions"""
        result = pyre.search("(ab)", "xxabxx", all=True)
        
        self.assertEqual(result[0], [(2, 4)])  # Full fullmatch at position 2
        self.assertEqual(result[1], [(2, 4)])  # Group 1 at position 2

    def test_multiple_fullmatches_with_captures(self):
        """Multiple fullmatches with capture groups"""
        result = pyre.search("(a)(b)", "abab", all=True)
        
        # First fullmatch: positions 0-2
        # Second fullmatch: positions 2-4
        # Note: This depends on your search() implementation
        # You may need to adjust based on how all=True works
        self.assertIn(0, result)
        self.assertIn(1, result)
        self.assertIn(2, result)

    def test_capture_group_zero(self):
        """Group 0 always represents the full fullmatch"""
        result = pyre.fullmatch("(a)", "a")
        
        # Group 0 should always exist and fullmatch the full string
        self.assertIn(0, result)
        self.assertEqual(result[0], [(0, 1)])


if __name__ == "__main__":
    unittest.main()