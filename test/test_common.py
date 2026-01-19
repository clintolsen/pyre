# pyre/test/test_common.py

import unittest
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pyre import Parser
import pyre

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

        result = pyre.match(expr, text)
        bool_result = bool(result)

        re_bool = re.fullmatch(pattern, text) is not None

        self.assertEqual(
            bool_result, re_bool,
            msg=f"Mismatch for pattern={pattern!r} text={text!r}: "
                f"pyre={bool_result}, re={re_bool}"
        )

    def assert_search_same_as_re(self, pattern, text):
        """
        Compare pyre's search behavior with Python's re.search.
        Only checks whether a match exists — not capture contents.
        """
        expr = self.compile(pattern)
        result = pyre.search(expr, text)
        bool_result = bool(result)
        re_bool = re.search(pattern, text) is not None
        self.assertEqual(
            bool_result, re_bool,
            msg=f"Mismatch for pattern={pattern!r} text={text!r}: "
                f"pyre={bool_result}, re={re_bool}"
        )