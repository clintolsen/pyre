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

    def test_match_returns_groups(self):
        """match() returns the same group shape as fullmatch()."""
        result = pyre.match("(a)b", "ab")

        self.assertEqual(result[0], [(0, 2)])
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


    def test_difference_drops_negated_captures(self):
        """Groups in the subtracted operand of r - s never report spans."""
        result = pyre.fullmatch("(a.)-(.b)", "ac")

        self.assertEqual(result, {0: [(0, 2)], 1: [(0, 2)]})

    def test_nested_difference_drops_negated_captures(self):
        """A nested difference keeps outer and left groups only."""
        result = pyre.fullmatch("x((a.)-(.b))", "xac")

        self.assertEqual(result, {0: [(0, 3)], 1: [(1, 3)], 2: [(1, 3)]})

    def test_complement_drops_captures(self):
        """Groups inside ~r describe non-matching strings and never report."""
        result = pyre.fullmatch("~((a)c)", "ab")

        self.assertEqual(result, {0: [(0, 2)]})

    def test_complement_drops_nullable_prefix_captures(self):
        """Markers reached through a nullable prefix under ~r never report."""
        result = pyre.fullmatch("~((x*)a)", "ab")

        self.assertEqual(result, {0: [(0, 2)]})

    def test_difference_drops_negated_captures_after_any(self):
        """Negated groups stay dropped when the left side is .*"""
        result = pyre.fullmatch(".*-x(a*)(b)", "xac")

        self.assertEqual(result, {0: [(0, 3)]})

    def test_alternation_drops_dead_branch_captures(self):
        """A branch that is alive mid-match but fails later reports nothing."""
        self.assertEqual(pyre.fullmatch("(a)b|(a)c", "ac"),
                         {0: [(0, 2)], 2: [(0, 1)]})
        self.assertEqual(pyre.fullmatch("(ab)|a(c)", "ac"),
                         {0: [(0, 2)], 2: [(1, 2)]})

    def test_alternation_prefers_leftmost_branch(self):
        """When both branches accept, only the leftmost reports captures."""
        self.assertEqual(pyre.fullmatch("(a.)|(.b)", "ab"),
                         {0: [(0, 2)], 1: [(0, 2)]})
        self.assertEqual(pyre.fullmatch("(a.)|(.b)", "cb"),
                         {0: [(0, 2)], 2: [(0, 2)]})

    def test_alternation_with_search(self):
        """Each search match reports only its own branch's group."""
        result = pyre.search("(a)b|(a)c", "xxacxxab", all=True)

        self.assertEqual(result, {0: [(2, 4), (6, 8)], 1: [(6, 7)], 2: [(2, 3)]})

    def test_xor_reports_only_matching_side(self):
        """r ^ s reports captures from whichever side matched."""
        self.assertEqual(pyre.fullmatch("(a.)^(.b)", "ac"),
                         {0: [(0, 2)], 1: [(0, 2)]})
        self.assertEqual(pyre.fullmatch("(a.)^(.b)", "cb"),
                         {0: [(0, 2)], 2: [(0, 2)]})

    def test_intersection_keeps_both_sides(self):
        """r & s matches the same span on both sides, so both report."""
        self.assertEqual(pyre.fullmatch("(a.)&(.c)", "ac"),
                         {0: [(0, 2)], 1: [(0, 2)], 2: [(0, 2)]})

    def test_simplified_away_group_keeps_its_number(self):
        """A group dropped by simplification does not renumber later groups."""
        self.assertEqual(pyre.fullmatch("(?:(a)-.*)?(b)", "b"),
                         {0: [(0, 1)], 2: [(0, 1)]})

    def test_captures_agree_with_python_re(self):
        """Path-consistent captures match Python's re where syntax overlaps."""
        import re

        cases = [
            ("((a)|(b))*", "ab"),
            ("(a*)(a*)", "aaa"),
            ("(a|ab)(c|bcd)(d*)", "abcd"),
            ("(x)?(xy)?", "xy"),
            ("(a+)+", "aa"),
            ("(?:(a)|b)*", "ab"),
            ("(a)|b", "b"),
            ("(a){0}(b)", "b"),
            ("(a)(b){0}(c)", "ac"),
            ("(?:(a){0}|(x))(b)", "xb"),
            ("(?:.*|(a))(b)", "xb"),
        ]
        for pattern, text in cases:
            with self.subTest(pattern=pattern, text=text):
                m = re.fullmatch(pattern, text)
                expected = {0: [m.span()]}
                for gid in range(1, m.re.groups + 1):
                    if m.span(gid) != (-1, -1):
                        expected[gid] = [m.span(gid)]

                self.assertEqual(pyre.fullmatch(pattern, text), expected)

    def test_group_names_do_not_leak_between_patterns(self):
        """A group name belongs to its own pattern, not to a same-numbered group elsewhere."""
        pyre.compile("(?P<OTHER>x)")
        pyre.compile("(x)")

        self.assertEqual(pyre.fullmatch("(?P<ID>a)", "a"),
                         {0: [(0, 1)], 1: [(0, 1)], "ID": [(0, 1)]})

    def test_lex_rule_order_wins_on_ties(self):
        """When two rules match the same token, the earlier rule wins."""
        kw_first = pyre.compile("(?P<KW>if)|(?P<ID>[a-z]+)|(?P<WS>\\s+)")
        id_first = pyre.compile("(?P<ID>[a-z]+)|(?P<KW>if)")

        self.assertEqual([t[0] for t in kw_first.lex("if\tiff")], ["KW", "WS", "ID"])
        self.assertEqual([t[0] for t in id_first.lex("if")], ["ID"])

if __name__ == "__main__":
    unittest.main()
