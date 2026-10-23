import sys
import argparse
from pathlib import Path
import logging

from . import search, fullmatch, compile
from . import regex
from . import util

LOG = logging.getLogger(__file__)


def main(argv=None):
    """
    Exit status follows grep: 0 if the pattern matched, 1 if it did not,
    and 2 for an error.
    """
    argparser = argparse.ArgumentParser()
    argparser.add_argument(
        '--debug', '-d',
        action='store_const',
        default=logging.INFO,
        const=logging.DEBUG,
        help='Enable debug logging'
    )
    argparser.add_argument(
        '--no-greedy',
        action='store_false',
        dest='greedy',
        default=True,
        help='Disable greedy matching (default: greedy)'
    )
    argparser.add_argument(
        '--all', '-a',
        action='store_true',
        help='Return all matches'
    )
    argparser.add_argument('regex', help='Regular expression')
    argparser.add_argument('target', help='String or file to search', nargs='?')

    args = argparser.parse_args(argv)

    logging.basicConfig(
        level=args.debug,
        format='%(message)s',
        stream=sys.stdout
    )

    if args.target:
        target = Path(args.target)
        if target.is_file():
            try:
                data = target.read_bytes()
                groups = search(args.regex, data, all=args.all, greedy=args.greedy)
            except (OSError, ValueError) as e:
                LOG.error(e)
                return 2

            LOG.debug(f'Groups: {groups}')
            flatten = [interval for group in groups.values() for interval in group]
            intervals = regex.merge_ranges(flatten, closed=False)
            LOG.debug(f'Merged intervals: {intervals}')

            # Write the file's own bytes, so text that isn't UTF-8 passes
            # through unchanged
            #
            sys.stdout.flush()
            out = sys.stdout.buffer
            i = 0
            for begin, end in intervals:
                out.write(data[i:begin])
                out.write(util.highlight(data[begin:end]))
                i = end
            out.write(data[i:])
            out.flush()
        else:
            try:
                groups = fullmatch(args.regex, args.target)
            except ValueError as e:
                LOG.error(e)
                return 2

            print(groups)

        return 0 if groups else 1
    else:
        try:
            print(compile(args.regex))
        except ValueError as e:
            LOG.error(e)
            return 2

        return 0
