# pyre/test/test_memory.py

import gc
import unittest
import sys
import weakref
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pyre
from pyre import dfa as _dfa


class TestMemory(unittest.TestCase):
    """Nodes and DFA states are freed once nothing uses them."""

    def test_dropped_dfa_is_freed(self):
        # Built directly, so the compiled-pattern cache doesn't keep it
        dfa = _dfa.compile(pyre.parse('(?P<w>[a-z]+)=(\\d+)z{3,7}'))
        self.assertTrue(dfa.search('ab=12zzz'))
        state = weakref.ref(dfa.initial)
        node = weakref.ref(dfa.initial.vector[0])
        del dfa
        gc.collect()
        self.assertIsNone(state())
        self.assertIsNone(node())

    def test_equal_nodes_are_one_object_while_in_use(self):
        a = pyre.parse('a(?:b|c)*')
        self.assertIs(pyre.parse('a(?:b|c)*'), a)


class TestPatternCache(unittest.TestCase):
    """As in Python's re, recent patterns are compiled once."""

    def test_same_pattern_same_dfa(self):
        self.assertIs(pyre.compile('cache[0-9]+test'), pyre.compile('cache[0-9]+test'))

    def test_cache_is_bounded(self):
        for i in range(pyre._MAXCACHE + 10):
            pyre.compile('bound%d' % i)
        self.assertEqual(len(pyre._cache), pyre._MAXCACHE)


if __name__ == '__main__':
    unittest.main()
