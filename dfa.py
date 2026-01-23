#
# dfa.py
#

import logging
LOG = logging.getLogger(__file__)

from . import util
from . import regex
from . parser import Parser
from . import regex

# Manage state transition information. In addition to keeping track of the next
# state, we will also house info about which particular states were used to
# compute the transition, generally a RegexDot or RegexSym.
#
class Goto:
    def __init__(self, _next, _states):
        self._next = _next
        self._states = _states
        self._events = None

    @property
    def events(self):
        if self._events is None:
            _events = set()

            for x in self._states:
                if x.ismarker:
                    for y in x.events:
                        _events.add(y)

            self._events = _events

        return self._events

    def __str__(self):
        return f'Goto(next={self._next.state_number} events={self.events})'

    def __repr__(self):
        return f'{self}'


def compile(expr):
    ''' Construct a DFA from a regular expression '''
    null_state = regex.RegexEmpty()
    default_goto = Goto(null_state, set())

    initial_state = expr
    LOG.debug(f'{initial_state.tree()}')
    dfa_states = set()
    todo_list = {initial_state}
    from collections import OrderedDict
    states = OrderedDict()

    while todo_list:
        current_state = todo_list.pop()

        classes = current_state.charset.get_int_sets()
        current_state.state_number = 'q%d' % len(dfa_states)
        LOG.debug(f'Current state {current_state.state_number}: {current_state}')

        markers = current_state.prefix_markers()
        ev = set()
        for m in markers:
            ev |= set(m.events)
        current_state.prefix_events = ev

        dfa_states.add(current_state)
        states[current_state] = current_state
        current_state.goto = [default_goto] * 256
        for charset in classes:
            if charset:
                char = chr(charset[0][0])

                accept = set()
                next_state = current_state.derive(char, accept)

                LOG.debug(f'Derivative of {current_state.state_number} of {repr(char)} => {next_state}')
                LOG.debug(f'Transition for {[regex.CharSet._fmt_char(x) for x in charset[0]]} is {accept}')

                goto = Goto(next_state, accept)
                LOG.debug(f'Goto events: {goto.events}')

                for rng in charset:
                    for code in range(rng[0], rng[-1] + 1):
                        current_state.goto[code] = goto

                if next_state not in dfa_states:
                    todo_list.add(next_state)


    if LOG.getEffectiveLevel() == logging.DEBUG:
        for state in states.values():
            state_label = state.state_number

            if state.isnullable():
                state_label = util.highlight(state_label)

            print(f'{state_label}: {state} (markers={state.prefix_markers()})')

            classes = state.charset.get_int_sets()

            for charset in classes:
                if charset:
                   goto = state.goto[charset[0][0]]
                   inside = regex.CharSet.fmt_ranges(charset)
                   print(f"    [{inside}] {goto}")

    LOG.debug('Total DFA states: %d' % len(dfa_states))
    LOG.debug('Total RE instances: %d' % len(regex.Regex._instance))

    return initial_state

from . import event
from .event import Event

class GroupInfo:
    """
    Tracks capture groups based on the set of active groups from each DFA step.

    Mirrors the logic originally in `search()`:
      - safe copies of active keys before computing diffs
      - supports multiple groups
    """
    def __init__(self):
        self.active = {}   # g -> start_index
        self.final  = {}   # g -> [(start, end), ...]

    def step(self, index: int, events: set[Event]):
        """
        index  = current character index in the input (same `index` you log in DFAStep)
        events = set of Event(...) from the transition (goto.events)
        """
        if not events:
            return set(), set()

        # Handle close events first 
        # 
        closes = [e for e in events if e.kind == event.CLOSE]
        opens  = [e for e in events if e.kind == event.OPEN]

        ended = set()
        started = set()

        for e in closes:
            gid = e.gid
            if gid in self.active:
                start = self.active[gid]
                self.final.setdefault(gid, []).append((start, index))
                del self.active[gid]
                ended.add(gid)
            else:
                # Optional: debug/log unexpected CLOSE
                # LOG.debug(f"Unmatched CLOSE({gid}) at index={index}")
                pass

        for e in opens:
            gid = e.gid
            # If you can get nested or repeated OPEN without CLOSE, decide policy.
            # For now: overwrite start (or ignore if already open).
            #
            self.active[gid] = index
            started.add(gid)

        return started, ended

    def finalize(self, match_start: int, match_end: int):
        out = {g: list(v) for g, v in self.final.items()}

        # Close any still-active groups at end of match
        #
        for gid, start in list(self.active.items()):
            out.setdefault(gid, []).append((start, match_end))

        # Whole match
        #
        out.setdefault(0, []).append((match_start, match_end))

        return out

from collections import namedtuple

DFAState = namedtuple("DFAState", "index char prev_state state goto")

def dfa_run(start_state, text, start_index=0):
    """
    Iterate a DFA over `text[start_index:]`.

    Yields DFAStep(index, char, prev_state, state, goto)
    where:
      - prev_state: state before reading char
      - state:      state after reading char
      - goto:       the Goto object used
    """
    state = start_state
    for i in range(start_index, len(text)):
        ch = text[i]
        goto = state.goto[ord(ch)]
        next_state = goto._next
        yield DFAState(
            index=i,
            char=ch,
            prev_state=state,
            state=next_state,
            goto=goto,
        )
        state = next_state


def match(expr, string, *, greedy=True):
    start_state = expr
    end_index = _span_from(start_state, string, 0, greedy=greedy)
    if end_index is None:
        return {}
    return _match_to_end(start_state, string, 0, end_index)


def fullmatch(expr, string):
    """
    Full-string match of `expr` against `string`.

    Returns:
        {} if no match

        Otherwise:
            {group_id: [(start, end), ...]}
        where start/end are 0-based indices into `string`, end-exclusive.
    """
    start_state = expr
    group_info = GroupInfo()
    state = start_state

    LOG.debug(f'Match: {state} against {string}')

    for step in dfa_run(start_state, string):
        state = step.state
        LOG.debug(f'Match: Step {step}')

        # Dead state
        #
        if state.isempty:
            return {}

        # Track capture groups
        group_info.step(step.index, step.goto.events)

    if not state.isnullable():
        return {}

    end_index = len(string)

    # finalize match span [0, end_index) and guarantee group 0 exists
    #
    finalized = group_info.finalize(0, end_index)

    return finalized

# Skip over known bad start characters
#
def _skip(start_state, s, offset):
    n = len(s)
    while offset < n and start_state.goto[ord(s[offset])]._next.isempty:
      offset += 1
    return offset

def _span_from(start_state, string, offset, *, greedy=True):
    """
    Return the best end index (exclusive) of a match starting at offset,
    or None if no match.
    """
    latest_end = None

    for step in dfa_run(start_state, string, start_index=offset):
        state = step.state

        if state.isempty:
            return latest_end

        if state.isnullable():
            latest_end = step.index + 1
            if not greedy:
                return latest_end

    return latest_end

def _match_to_end(start_state, string, offset, end_index):
    """
    Run DFA from offset up to end_index and compute capture groups.
    """
    group_info = GroupInfo()
    last_state = start_state

    for step in dfa_run(start_state, string, start_index=offset):
        if step.index >= end_index:
            break

        state = step.state
        if state.isempty:
            break

        group_info.step(step.index, step.goto.events)
        last_state = state

    # apply boundary CLOSE events at the match endpoint
    close_events = {e for e in last_state.prefix_events if e.kind == event.CLOSE}
    if close_events:
        group_info.step(end_index, close_events)

    return group_info.finalize(offset, end_index)

def search(expr, string, *, greedy=True, all=False):
    """
    Search for `expr` in `string`.

    Greedy: Find the longest match.

    If all is False (default):
        - returns {} if no match
        - otherwise returns {group_id: [(start, end)]} for the first match

    If all is True:
        - returns {} if no match
        - otherwise returns {group_id: [(start, end), ...]} where each
          (start, end) is one non-overlapping match for that group.
    """
    start_state = expr
    n = len(string)

    if not all:
        offset = _skip(start_state, string, 0)
        while offset < n:
            end_index = _span_from(
                start_state, string, offset, greedy=greedy
            )

            if end_index is not None:
                return _match_to_end(
                    start_state, string, offset, end_index
                )

            offset = _skip(start_state, string, offset + 1)

        return {}
    all_groups = {}
    offset = _skip(start_state, string, 0)

    while offset < n:
        end_index = _span_from(
            start_state, string, offset, greedy=greedy
        )

        if end_index is None:
            offset = _skip(start_state, string, offset + 1)
            continue

        groups = _match_to_end(
            start_state, string, offset, end_index
        )

        for gid, intervals in groups.items():
            all_groups.setdefault(gid, []).extend(intervals)

        offset = _skip(start_state, string, end_index)

    return all_groups
