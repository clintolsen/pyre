# pyre/test/test_unicode.py

import unittest
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pyre
from pyre import regex as rx


class TestCharacters(unittest.TestCase):
    """Patterns match code points, whatever their UTF-8 length."""

    def test_dot_matches_one_character_of_any_length(self):
        for ch in ['a', 'é', '→', '🙂', '\udcff', '\x00', '\U0010ffff']:
            with self.subTest(ch=ch):
                self.assertEqual(pyre.fullmatch('.', ch), {0: [(0, 1)]})
                self.assertEqual(pyre.fullmatch('..', ch), {})

    def test_literals(self):
        self.assertTrue(pyre.fullmatch('a→b', 'a→b'))
        self.assertTrue(pyre.fullmatch('🙂+', '🙂🙂🙂'))
        self.assertFalse(pyre.fullmatch('→', '←'))

    def test_class_ranges(self):
        greek = pyre.compile('[α-ω]+')
        self.assertTrue(greek.fullmatch('λογος'))
        self.assertFalse(greek.fullmatch('λόγος'))  # ό is outside α-ω
        self.assertTrue(pyre.fullmatch('[é-🙂]', '→'))
        self.assertFalse(pyre.fullmatch('[é-🙂]', 'e'))

    def test_negated_class_includes_other_scripts(self):
        self.assertTrue(pyre.fullmatch('[^a]', 'é'))
        self.assertTrue(pyre.fullmatch('[^→]', '🙂'))
        self.assertFalse(pyre.fullmatch('[^→]', '→'))

    def test_escapes_are_ascii(self):
        """\\d, \\w and \\s are ASCII only, as with re.ASCII."""
        self.assertFalse(pyre.fullmatch(r'\w', 'é'))
        self.assertTrue(pyre.fullmatch(r'\W', 'é'))
        self.assertFalse(pyre.fullmatch(r'\d', '٣'))
        self.assertTrue(pyre.fullmatch(r'[^\s]', '→'))

    def test_full_class_is_dot(self):
        self.assertIs(pyre.parse(r'[\s\S]'), rx.RegexDot())

    def test_printing(self):
        for pattern in ['[α-ω]', '[^a]', 'é', '[a-c\\]]']:
            with self.subTest(pattern=pattern):
                printed = str(pyre.parse(pattern))
                self.assertTrue(pyre.equal(printed, pattern), printed)
        self.assertEqual(str(pyre.parse('[α-ω]')), '[α-ω]')
        self.assertEqual(str(pyre.parse('[^a]')), '[^a]')


class TestComplement(unittest.TestCase):
    """~r is the valid UTF-8 text that r does not match."""

    def test_complement_matches_whole_characters(self):
        self.assertEqual(pyre.fullmatch('~a', '→'), {0: [(0, 1)]})
        self.assertEqual(pyre.fullmatch('~→', '→'), {})
        self.assertEqual(pyre.fullmatch('~→', '→→'), {0: [(0, 2)]})

    def test_invalid_halves_never_make_a_character(self):
        """Over raw bytes, ~(.*) would hold \\xe2 and \\x86\\x92, which spell →."""
        self.assertTrue(pyre.isempty('~(?:.*)'))
        self.assertTrue(pyre.isempty('~(?:.*)~(?:.*)'))
        self.assertEqual(pyre.fullmatch('~(?:.*)~(?:.*)', '→'), {})

    def test_set_operators(self):
        self.assertTrue(pyre.equal('~~é', 'é'))
        self.assertTrue(pyre.equal('.-a', '[^a]'))
        self.assertTrue(pyre.subset('[α-ω]', '~[a-z]'))


class TestOffsets(unittest.TestCase):
    """Spans count characters for str and bytes for bytes."""

    def test_search_counts_characters(self):
        self.assertEqual(pyre.search('a', 'x → a'), {0: [(4, 5)]})
        self.assertEqual(pyre.search('.', 'aé🙂', all=True),
                         {0: [(0, 1), (1, 2), (2, 3)]})

    def test_groups_count_characters(self):
        self.assertEqual(pyre.fullmatch('(é)(?P<x>.)', 'é🙂'),
                         {0: [(0, 2)], 1: [(0, 1)], 2: [(1, 2)], 'x': [(1, 2)]})

    def test_surrogates_are_characters(self):
        """A str can hold lone surrogates, as decoding a bad filename leaves."""
        name = b'caf\xff.txt'.decode('utf-8', 'surrogateescape')
        self.assertEqual(pyre.fullmatch(r'caf.\.txt', name), {0: [(0, 8)]})

    def test_bytes_count_bytes(self):
        self.assertEqual(pyre.search('é', 'café'.encode()), {0: [(3, 5)]})
        self.assertEqual(pyre.fullmatch('.', 'é'.encode()), {0: [(0, 2)]})

    def test_invalid_bytes_never_match(self):
        self.assertEqual(pyre.search('.+', b'a\xffb\xe2\x86', all=True),
                         {0: [(0, 1), (2, 3)]})
        self.assertEqual(pyre.fullmatch('~a', b'\xff'), {})

    def test_other_types_are_rejected(self):
        with self.assertRaises(TypeError):
            pyre.search('a', 42)


class TestLexer(unittest.TestCase):
    RULES = [('WORD', '(?P<first>[α-ω])[α-ω]*'), ('SPACE', r'\ +'), ('OTHER', '.')]

    def test_tokens_count_characters(self):
        tokens = list(pyre.lexer(self.RULES).lex('αβ γ→'))

        self.assertEqual([tuple(t) for t in tokens],
                         [('WORD', 'αβ', 0, 2), ('SPACE', ' ', 2, 3),
                          ('WORD', 'γ', 3, 4), ('OTHER', '→', 4, 5)])
        self.assertEqual(tokens[0].groups['first'], [(0, 1)])
        self.assertEqual(tokens[2].group('first'), 'γ')

    def test_bytes_tokens_are_bytes(self):
        tokens = list(pyre.lexer(self.RULES).lex('αβ →'.encode()))

        self.assertEqual([tuple(t) for t in tokens],
                         [('WORD', 'αβ'.encode(), 0, 4), ('SPACE', b' ', 4, 5),
                          ('OTHER', '→'.encode(), 5, 8)])
        self.assertEqual(tokens[0].group('first'), 'α'.encode())


class TestAgainstRe(unittest.TestCase):
    """Random patterns agree with Python's re on mixed-script text."""

    ALPHA = ['a', 'b', 'é', 'λ', '→', '🙂', '\udcff']
    CLASSES = ['[ab]', '[^a]', '[α-ω]', '[^→]', '[a-é]', '[é-🙂]', r'[\d\s]', r'\W', '.']

    def test_fullmatch_agrees_with_re(self):
        rng = random.Random(7)

        def gen(depth=0):
            r = rng.random()
            if depth > 3 or r < 0.3:
                return rng.choice(self.ALPHA + self.CLASSES)
            if r < 0.55:
                return gen(depth + 1) + gen(depth + 1)
            if r < 0.7:
                return f'(?:{gen(depth + 1)}|{gen(depth + 1)})'
            return f'(?:{gen(depth + 1)}){rng.choice("*+?")}'

        texts = [''.join(rng.choice(self.ALPHA + ['x', ' ', 'ω', '\U0001F600'])
                         for _ in range(rng.randint(0, 5))) for _ in range(40)]

        for _ in range(60):
            pattern = gen()
            expected = re.compile(pattern, re.DOTALL | re.ASCII)
            dfa = pyre.compile(pattern)
            complement = pyre.compile(f'~(?:{pattern})')
            for text in texts:
                m = expected.fullmatch(text)
                with self.subTest(pattern=pattern, text=text):
                    self.assertEqual(dfa.fullmatch(text), {0: [m.span()]} if m else {})
                    self.assertEqual(bool(complement.fullmatch(text)), m is None)


if __name__ == "__main__":
    unittest.main()
