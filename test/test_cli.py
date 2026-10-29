# pyre/test/test_cli.py

import unittest
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'pyre'

ON, OFF = b'\033[07m', b'\033[0m'


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True)


class TestFile(unittest.TestCase):
    """A file is searched and printed as bytes, with every match highlighted."""

    def search(self, pattern, data, *flags):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'input'
            path.write_bytes(data)
            return run(*flags, pattern, str(path))

    def test_highlights_every_match(self):
        result = self.search('ab', b'xab ab\n')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b'x' + ON + b'ab' + OFF + b' ' + ON + b'ab' + OFF + b'\n')

    def test_no_match_prints_the_file_unchanged(self):
        result = self.search('zz', b'abc\n')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, b'abc\n')

    def test_keeps_the_last_line_without_a_newline(self):
        result = self.search('b', b'abc')
        self.assertEqual(result.stdout, b'a' + ON + b'b' + OFF + b'c')

    def test_matches_utf8_characters(self):
        text = 'x = λογος\n'.encode()
        result = self.search('[α-ω]+', text)
        self.assertEqual(result.stdout, b'x = ' + ON + 'λογος'.encode() + OFF + b'\n')

    def test_invalid_utf8_passes_through(self):
        data = b'caf\xc3\xa9 \xff\xfe\n'
        result = self.search('é', data)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b'caf' + ON + b'\xc3\xa9' + OFF + b' \xff\xfe\n')

    def test_empty_matches_highlight_nothing(self):
        result = self.search('b*', b'abc\n')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b'a' + ON + b'b' + OFF + b'c\n')

    def test_dot_skips_invalid_bytes(self):
        result = self.search('.', b'\xff\xfe\x80')
        self.assertEqual(result.returncode, 1)


class TestStatus(unittest.TestCase):
    """Exit status follows grep."""

    def test_string_target(self):
        self.assertEqual(run('a+', 'aaa').returncode, 0)
        self.assertEqual(run('a+', 'b').returncode, 1)

    def test_bad_pattern(self):
        self.assertEqual(run('(a', 'a').returncode, 2)

    def test_missing_file_is_a_string(self):
        self.assertEqual(run('a', '/nonexistent/a').returncode, 1)


if __name__ == '__main__':
    unittest.main()
