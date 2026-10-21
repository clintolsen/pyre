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
# Negated operands (the right side of r - s, all of ~r) describe strings that
# must not match, so they are derived as opaque Brzozowski terms and never
# contribute markers. Xor is split into (r - s) | (s - r) so the side that
# matched keeps its captures.
#

from . import event
from . import regex as rx

_derive_branches_cache = {}
_nullable_markers_cache = {}

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

        # Push right first so the left child is visited first.
        #
        stack.extend(reversed(_children(node)))

    return numbers


def _children(expr):
    if hasattr(expr, 'left') and hasattr(expr, 'right'):
        return (expr.left, expr.right)
    if hasattr(expr, 'expr'):
        return (expr.expr,)
    return ()


def nullable_markers(expr):
    """
    Like Regex.nullable(), but reports which markers the empty match crosses.

    Returns the markers on the highest-priority empty path through expr, as a
    tuple in traversal order, or None if expr is not nullable.
    """
    try:
        result = _nullable_markers_cache[expr]
    except KeyError:
        result = _nullable_markers(expr)
        _nullable_markers_cache[expr] = _NOT_NULLABLE if result is None else result
        return result

    return None if result is _NOT_NULLABLE else result


def _nullable_markers(e):
    if e.ismarker:
        return (e,)

    if e.isepsilon or isinstance(e, (rx.RegexStar,)):
        return ()

    if isinstance(e, rx.RegexOr):
        left = nullable_markers(e.left)
        return left if left is not None else nullable_markers(e.right)

    if isinstance(e, (rx.RegexConcat, rx.RegexAnd)):
        left = nullable_markers(e.left)
        if left is None:
            return None
        right = nullable_markers(e.right)
        if right is None:
            return None
        return left + right

    if isinstance(e, rx.RegexPlus):
        return nullable_markers(e.expr)

    if isinstance(e, rx.RegexOpt):
        inner = nullable_markers(e.expr)
        return inner if inner is not None else ()

    if isinstance(e, rx.RegexDiff):
        if e.right.isnullable():
            return None
        return nullable_markers(e.left)

    if isinstance(e, rx.RegexNot):
        return None if e.expr.isnullable() else ()

    if isinstance(e, rx.RegexXor):
        left_ok = e.left.isnullable()
        right_ok = e.right.isnullable()
        if left_ok == right_ok:
            return None
        return nullable_markers(e.left) if left_ok else nullable_markers(e.right)

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
    key = (expr, ch)
    try:
        return _derive_branches_cache[key]
    except KeyError:
        pass

    result = [(m, t) for m, t in _derive_branches(expr, ch) if not t.isempty]
    _derive_branches_cache[key] = result
    return result


def _derive_branches(e, ch):
    if e.isempty or e.isepsilon or e.ismarker:
        return []

    if isinstance(e, (rx.RegexSym, rx.RegexDot)):
        return [((), rx.RegexEpsilon())] if not e.derive(ch).isempty else []

    if isinstance(e, rx.RegexOr):
        return derive_branches(e.left, ch) + derive_branches(e.right, ch)

    if isinstance(e, rx.RegexConcat):
        out = [(m, rx.RegexConcat(t, e.right)) for m, t in derive_branches(e.left, ch)]
        skipped = nullable_markers(e.left)
        if skipped is not None:
            out += [(skipped + m, t) for m, t in derive_branches(e.right, ch)]
        return out

    if isinstance(e, rx.RegexStar):
        return [(m, rx.RegexConcat(t, e)) for m, t in derive_branches(e.expr, ch)]

    if isinstance(e, rx.RegexPlus):
        star = rx.RegexStar(e.expr)
        return [(m, rx.RegexConcat(t, star)) for m, t in derive_branches(e.expr, ch)]

    if isinstance(e, rx.RegexOpt):
        return derive_branches(e.expr, ch)

    if isinstance(e, rx.RegexAnd):
        return [
            (lm + rm, rx.RegexAnd(lt, rt))
            for lm, lt in derive_branches(e.left, ch)
            for rm, rt in derive_branches(e.right, ch)
        ]

    if isinstance(e, rx.RegexDiff):
        negated = e.right.derive(ch)
        return [(m, rx.RegexDiff(t, negated)) for m, t in derive_branches(e.left, ch)]

    if isinstance(e, rx.RegexNot):
        return [((), rx.RegexNot(e.expr.derive(ch)))]

    if isinstance(e, rx.RegexXor):
        return (derive_branches(rx.RegexDiff(e.left, e.right), ch) +
                derive_branches(rx.RegexDiff(e.right, e.left), ch))

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
            for markers, nxt in derive_branches(term, ch):
                if nxt in seen:
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
