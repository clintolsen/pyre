import sys
import argparse
from pathlib import Path
import logging

from . import search, fullmatch
from . import regex
from . import util

LOG = logging.getLogger(__file__)


def main(argv=None):
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
    argparser.add_argument('target', help='String or file to search')

    args = argparser.parse_args(argv)

    logging.basicConfig(
        level=args.debug,
        format='%(message)s',
        stream=sys.stdout
    )

    target = Path(args.target)
    if target.is_file():
        with open(target) as f:
            file = f.read()

        try:
            groups = search(args.regex, file, all=args.all, greedy=args.greedy)
        except ValueError as e:
            LOG.error(e)
            return 1

        LOG.debug(f'Groups: {groups}')
        flatten = [interval for group in groups.values() for interval in group]
        intervals = regex.merge_intervals(flatten)
        LOG.debug(f'Merged intervals: {intervals}')

        i = 0
        while i < len(file):
            begin = -1
            end = -1

            if intervals:
                begin, end = intervals.pop(0)

            print(file[i:begin], end='')

            if begin > -1:
                print(util.highlight(file[begin:end]), end='')
                i = end
            else:
                print()
                break
    else:
        try:
            groups = fullmatch(args.regex, args.target)
        except ValueError as e:
            LOG.error(e)
            return 1

        print(groups)
