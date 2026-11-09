#
# capture.py
#
# Capture-group extraction along a single accepting path.
#
# The DFA built from Brzozowski derivatives decides whether text matches and
# where a match ends, but its states merge every alternative together, so a
# transition cannot tell which branch produced a marker. A branch that dies
# later would still leave its markers behind.
#
# Here we re-run the matched span through partial (Antimirov) derivatives,
# which keep alternatives as separate, ordered terms. Each term carries its
# own capture state, and when two branches reach the same term only the
# higher-priority one survives, Pike VM style. Markers are therefore only
# reported for the branch that actually accepts.
#
# Negated operands (all but the first of r - s, and all of ~r) describe
# strings that must not match, so they are derived as opaque Brzozowski
# terms and never contribute markers. Xor is split into (r - s) | (s - r)
# so the side that matched keeps its captures.
#

import functools

from . import event
from . import regex as rx

_NOT_NULLABLE = object()


def group_numbers(expr):
    """
    Map each group id in expr to the number users see.

    Within one parsed pattern a group's number is the position of its '('
    in the pattern string, so a group that simplifies away, as in (a){0}(b)
    or (?:.*|(a))(b), still holds its number and (b) is group 2. When
    patterns are composed, each one's groups are numbered after those of
    the patterns that appear before it, left to right, so
    parse("(a)") | parse("(b)") numbers its groups exactly like
    parse("(a)|(b)"). An operand whose groups have all simplified away
    leaves no trace, so it cannot hold its numbers.
    """
    numbers = {}
    offsets = {}
    total = 0
    visited = set()
    stack = [expr]

    while stack:
        node = stack.pop()
        if node in visited:
            continue
        visited.add(node)

        if node.ismarker:
            for ev in node.events:
                if ev.kind == event.OPEN and ev.gid not in numbers:
                    source, index = ev.gid
                    if source not in offsets:
                        offsets[source] = total
                        total += source.count
                    numbers[ev.gid] = offsets[source] + index
            continue

        # Push the operands in reverse so the first is visited first.
        #
        stack.extend(reversed(node.args))

    return numbers


def nullable_markers(expr):
    """
    Like Regex.nullable(), but reports which markers the empty match crosses.

    Returns the markers on the highest-priority empty path through expr, as a
    tuple in traversal order, or None if expr is not nullable.
    """
    result = expr._markers
    if result is None:
        result = _nullable_markers(expr)
        expr._markers = _NOT_NULLABLE if result is None else result
        return result

    return None if result is _NOT_NULLABLE else result


def _nullable_markers(e):
    if e.ismarker:
        return (e,)

    if e.isepsilon:
        return ()

    if isinstance(e, rx.RegexOr):
        for arg in e.args:
            markers = nullable_markers(arg)
            if markers is not None:
                return markers
        return None

    if isinstance(e, (rx.RegexConcat, rx.RegexAnd)):
        out = ()
        for arg in e.args:
            markers = nullable_markers(arg)
            if markers is None:
                return None
            out += markers
        return out

    if isinstance(e, rx.RegexPlus):
        return nullable_markers(e.expr)

    # A repeat that could go on takes one more, empty, iteration if its body
    # can match empty, as re does, so (a*)* reports group 1 at the end of
    # "aa" as (2, 2)
    #
    if isinstance(e, (rx.RegexStar, rx.RegexOpt)) or (isinstance(e, rx.RegexRepeat) and e.lo == 0):
        inner = nullable_markers(e.expr)
        return inner if inner is not None else ()

    if isinstance(e, rx.RegexRepeat):
        return nullable_markers(e.expr)

    if isinstance(e, rx.RegexDiff):
        first, *removed = e.args
        for arg in removed:
            if arg.isnullable():
                return None
        return nullable_markers(first)

    if isinstance(e, rx.RegexNot):
        return None if e.expr.isnullable() else ()

    # Without captures, ⊕ may have many operands; it has no markers to report
    #
    if isinstance(e, rx.RegexXor):
        if not e.hascaptures:
            return () if e.isnullable() else None
        left, right = e.args
        left_ok = left.isnullable()
        right_ok = right.isnullable()
        if left_ok == right_ok:
            return None
        return nullable_markers(left) if left_ok else nullable_markers(right)

    # Empty, Sym, Dot
    #
    return None


def derive_branches(expr, ch):
    """
    Like Regex.derive(), but keeps each branch separate instead of merging
    them into one term. These are partial (Antimirov) derivatives.

    Returns an ordered list of (markers, term), highest priority first.
    markers is the tuple of markers crossed before consuming ch on that
    branch, and term is what remains of that branch afterward.
    """
    return [branch for branch in _branches(expr, ch) if branch[1] is not None]


def _branches(expr, ch):
    """
    The branches of derive_branches(), plus at most one exit (markers, None)
    where expr may stop without consuming ch, placed at its priority among
    the branches. markers on the exit are those of nullable_markers(expr).

    The exit's place matters when something follows expr: in (a?|b)(b?) the
    empty a? outranks the b alternative, so on "b" the following (b?) must
    take the character before (a?|b) does, as re would.
    """
    try:
        return expr._branches[ch]
    except KeyError:
        pass

    result = []
    exited = False
    for markers, term in _derive_branches(expr, ch):
        if term is None:
            # A later exit reaches the same continuation with lower priority
            #
            if exited:
                continue
            exited = True
        elif term.isempty:
            continue
        result.append((markers, term))

    expr._branches[ch] = result
    return result


def _exit_last(e, branches):
    """ branches, then an exit if e is nullable """
    markers = nullable_markers(e)
    return branches if markers is None else branches + [(markers, None)]


def _derive_branches(e, ch):
    if e.isempty:
        return []

    if e.isepsilon:
        return [((), None)]

    if e.ismarker:
        return [((e,), None)]

    # A character's derivative is ε, or the rest of a longer character
    #
    if isinstance(e, (rx.RegexCodePoints, rx.RegexByte)):
        return [((), e.derive(ch))]

    if isinstance(e, rx.RegexOr):
        return [branch for arg in e.args for branch in _branches(arg, ch)]

    # Where an operand can stop, the branches of what follows it take its
    # place, after the markers its empty match crosses
    #
    if isinstance(e, rx.RegexConcat):
        first, rest = e.args[0], rx.RegexConcat.of(e.args[1:])
        out = []
        for m, t in _branches(first, ch):
            if t is not None:
                out.append((m, rx.RegexConcat(t, rest)))
            else:
                out += [(m + rm, rt) for rm, rt in _branches(rest, ch)]
        return out

    # An empty iteration ends the repeat where it happens, as in re, so an
    # exit in the body stays put. Otherwise the repeat stops after every
    # iteration that consumes, as a greedy repeat does.
    #
    if isinstance(e, (rx.RegexStar, rx.RegexPlus, rx.RegexRepeat)):
        if isinstance(e, rx.RegexStar):
            rest = e
        elif isinstance(e, rx.RegexPlus):
            rest = rx.RegexStar(e.expr)
        else:
            rest = e.rest()
        out = [(m, t if t is None else rx.RegexConcat(t, rest))
               for m, t in _branches(e.expr, ch)]
        optional = isinstance(e, rx.RegexStar) or (isinstance(e, rx.RegexRepeat) and e.lo == 0)
        if optional and all(t is not None for _, t in out):
            out.append(((), None))
        return out

    if isinstance(e, rx.RegexOpt):
        out = list(_branches(e.expr, ch))
        if all(t is not None for _, t in out):
            out.append(((), None))
        return out

    if isinstance(e, rx.RegexAnd):
        out = derive_branches(e.args[0], ch)
        for arg in e.args[1:]:
            out = [
                (lm + rm, rx.RegexAnd(lt, rt))
                for lm, lt in out
                for rm, rt in derive_branches(arg, ch)
            ]
        return _exit_last(e, out)

    if isinstance(e, rx.RegexDiff):
        first, *removed = e.args
        negated = [arg.derive(ch) for arg in removed]
        keep_exit = not any(arg.isnullable() for arg in removed)
        return [
            (m, functools.reduce(rx.RegexDiff, [t] + negated) if t is not None else None)
            for m, t in _branches(first, ch)
            if t is not None or keep_exit
        ]

    if isinstance(e, rx.RegexNot):
        return _exit_last(e, [((), e.derive(ch))])

    if isinstance(e, rx.RegexXor):
        if not e.hascaptures:
            return _exit_last(e, [((), e.derive(ch))])
        # Either side's branches, with the other side removed
        #
        left, right = e.args
        left_ok, right_ok = left.isnullable(), right.isnullable()
        out = [(m, rx.RegexDiff(t, right.derive(ch)) if t is not None else None)
               for m, t in _branches(left, ch) if t is not None or not right_ok]
        return out + [(m, rx.RegexDiff(t, left.derive(ch)) if t is not None else None)
                      for m, t in _branches(right, ch) if t is not None or not left_ok]

    raise TypeError(f'derive_branches: unsupported node {type(e).__name__}')


class _Caps:
    """
    Immutable capture state for one thread: completed spans, open starts,
    and group names. Updates return a new object only when something changes.
    """
    __slots__ = ('spans', 'opened', 'names')

    def __init__(self, spans=None, opened=None, names=None):
        self.spans = spans or {}
        self.opened = opened or {}
        self.names = names or {}

    def apply(self, markers, index):
        if not markers:
            return self

        spans = dict(self.spans)
        opened = dict(self.opened)
        names = self.names

        for marker in markers:
            # Closes before opens, so )( at one index ends a group before
            # the next one starts.
            #
            events = sorted(marker.events, key=lambda ev: ev.kind != event.CLOSE)
            for ev in events:
                if ev.kind == event.CLOSE:
                    if ev.gid in opened:
                        spans[ev.gid] = (opened.pop(ev.gid), index)
                else:
                    if ev.name and names.get(ev.gid) != ev.name:
                        names = {**names, ev.gid: ev.name}
                    opened[ev.gid] = index

        return _Caps(spans, opened, names)

    def finalize(self, start, end, numbers):
        """
        Build the result dict, translating internal group ids to the
        public numbers from group_numbers().
        """
        out = {numbers[gid]: [span] for gid, span in self.spans.items()}
        out[0] = [(start, end)]

        named = {
            name: [self.spans[gid]]
            for gid, name in self.names.items()
            if gid in self.spans
        }

        return {**named, **out}


def captures(expr, text, start, end, numbers):
    """
    Capture groups for text[start:end] fully matching expr, taken from the
    highest-priority accepting path. Returns {} if there is no such path.
    numbers is the mapping from group_numbers(expr).
    """
    threads = [(expr, _Caps())]

    for index in range(start, end):
        ch = text[index]
        seen = set()
        advanced = []

        for term, caps in threads:
            for markers, nxt in _branches(term, ch):
                if nxt is None or nxt in seen:
                    continue
                seen.add(nxt)
                advanced.append((nxt, caps.apply(markers, index)))

        threads = advanced
        if not threads:
            return {}

    for term, caps in threads:
        tail = nullable_markers(term)
        if tail is not None:
            return caps.apply(tail, end).finalize(start, end, numbers)

    return {}
