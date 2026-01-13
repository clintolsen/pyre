#
# dfa.py
#

import logging
LOG = logging.getLogger(__file__)

from . import util
from . import regex

# Manage state transition information. In addition to keeping track of the next
# state, we will also house info about which particular states were used to
# compute the transition, generally a RegexDot or RegexSym.
#
class Goto:
    def __init__(self, _next, _states):
        self._next = _next
        self._states = _states
        self._group = None

    # Collect the group information and return it as a set. We take the union of
    # all the groups in all the states.
    #
    @property
    def group(self):
        if self._group is None:
            _group = set()

            for x in self._states:
                for y in x.group:
                    _group.add(y)

            self._group = _group

        return self._group

    def __str__(self):
        return f'Goto(next={self._next.state_number} group={self.group})'


def make_char(code):
    char = chr(code)

    if not char.isprintable():
        char = repr(char)

    return char

def compile(expr):
    ''' Construct a DFA from a regular expression '''
    null_state = regex.RegexEmpty()
    default_goto = Goto(null_state, set())

    initial_state = expr
    dfa_states = set()
    todo_list = {initial_state}
    from collections import OrderedDict
    states = OrderedDict()

    while todo_list:
        current_state = todo_list.pop()

        classes = current_state.charset.get_int_sets()
        current_state.state_number = 'q%d' % len(dfa_states)
        LOG.debug(f'Current state {current_state.state_number}: {repr(current_state)}')
        dfa_states.add(current_state)
        states[current_state] = current_state
        current_state.goto = [default_goto] * 256
        for charset in classes:
            if charset:
                char = chr(charset[0][0])

                accept = set()
                next_state = current_state.derive(char, accept)

                LOG.debug(f'Derivative of {current_state.state_number} of {repr(char)} => {next_state}')
                LOG.debug(f'Transition for {[make_char(x) for x in charset[0]]} is {accept}')

                goto = Goto(next_state, accept)

                for rng in charset:
                    for ch in range(rng[0], rng[-1] + 1):
                        current_state.goto[ch] = goto

                if next_state not in dfa_states:
                    todo_list.add(next_state)


    if LOG.getEffectiveLevel() == logging.DEBUG:
        for state in states.values():
            state_label = state.state_number

            if state.isnullable():
                state_label = util.highlight(state_label)

            print(f'{state_label}: {state}')

            classes = state.charset.get_int_sets()

            for charset in classes:
                if charset:
                    print('    [', end='')
                    goto = state.goto[charset[0][0]]
                    for i, rng in enumerate(charset):
                        # Separator
                        #
                        if i:
                            print(', ', end='')
                        if len(rng) == 2:
                            print('%s - %s' % (make_char(rng[0]), make_char(rng[1])), end='')
                        else:
                            print('%s' % (make_char(rng[0])), end='')

                    print(f'] {goto}')

    LOG.debug('Total DFA states: %d' % len(dfa_states))
    LOG.debug('Total RE instances: %d' % len(regex.Regex._instance))

    return initial_state


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

    def step(self, index, group_set):
        """
        Process one DFA step.

        `index`    = current character index in the input
        `group_set`= set of group ids active on this transition (goto.group)

        Returns (started, ended) for introspection/debug if you care.
        """

        # Groups starting: g in group_set but not in active
        #
        current_active = set(self.active.keys())
        started = group_set - current_active
        for g in started:
            self.active[g] = index

        # Groups ending: g in active but not in group_set
        #
        current_active = set(self.active.keys())
        ended = current_active - group_set
        for g in ended:
            start = self.active[g]
            self.final.setdefault(g, []).append((start, index)) # self.final[g] = [(start, index)]
            del self.active[g]

        return started, ended

    def finalize(self, match_start: int, match_end: int):
        """
        Produce groups for a completed match [start_index, end_index),
        and always include group 0.
        """
        out = {g: list(v) for g, v in self.final.items()} 

        # close any still-active groups at end_index
        for g, start in self.active.items():
            out.setdefault(g, []).append((start, match_end))

        # group 0 is the whole match, no excuses
        out.setdefault(0, [(match_start, match_end)]) # out.setdefault(g, []).append((s, index))

        return out

from collections import namedtuple

DFAState = namedtuple("DFAState", "index char prev_state state goto group")

def dfa_run(start_state, text, start_index=0):
    """
    Iterate a DFA over `text[start_index:]`.

    Yields DFAStep(index, char, prev_state, state, goto, group)
    where:
      - prev_state: state before reading char
      - state:      state after reading char
      - goto:       the Goto object used
      - group:      goto.group
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
            group=goto.group,
        )
        state = next_state


def match(expr, string):
    """
    Full-string match of `expr` against `string`.

    Returns:
        {} if no match

        Otherwise:
            {group_id: [(start, end), ...]}
        where start/end are 0-based indices into `string`, end-exclusive.
    """
    start_state = compile(expr)   # yo, straight-up compile, no .* nonsense
    group_info = GroupInfo()
    state = start_state

    for step in dfa_run(start_state, string):
        state = step.state

        # dead state? yeah it's cooked, bounce
        if state.isempty:
            return {}

        # track dem capture groups like a hawk
        group_info.step(step.index, step.group)

    # end of input: full match only if we're in accept land
    if not state.isnullable():
        return {}

    end_index = len(string)

    # finalize match span [0, end_index) and guarantee group 0 exists
    finalized = group_info.finalize(0, end_index)

    return finalized


def _match_from(start_state, string, offset, *, greedy: bool = True):
    """
    Run the DFA starting at `offset` and return the best match from that start.

    Returns:
        (groups, end_index, stop_at)

    Where:
        groups   : dict[group_id] -> list[(start, end)]  (or None if no match)
        end_index: match end (exclusive) (or None)
        stop_at  : index where the run stopped:
                    - if it died: the index that produced ∅
                    - if it hit EOF: the last processed index (or None if no chars processed)
    """
    group_info = GroupInfo()
    latest = None  # (groups, end_index)
    last_step_index = None

    for step in dfa_run(start_state, string, start_index=offset):
        last_step_index = step.index
        state = step.state

        if state.isempty:
            stop_at = step.index
            if latest is None:
                return None, None, stop_at
            groups, end_index = latest
            return groups, end_index, stop_at

        group_info.step(step.index, step.group)

        if state.isnullable():
            end_index = step.index + 1
            groups = group_info.finalize(offset, end_index)
            latest = (groups, end_index)

            if not greedy:
                return groups, end_index, None

    # EOF
    if latest is None:
        return None, None, last_step_index
    groups, end_index = latest
    return groups, end_index, last_step_index


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
    start_state = compile(expr)
    n = len(string)

    if not all:
        offset = 0
        while offset < n:
            groups, end_index, stop_at = _match_from(
                start_state, string, offset, greedy=greedy
            )

            if groups is not None:
                return groups

            offset = (stop_at + 1) if stop_at is not None else (offset + 1)

        return {}

    # all=True: collect non-overlapping matches
    all_groups = {}
    offset = 0
    while offset < n:
        groups, end_index, stop_at = _match_from(
            start_state, string, offset, greedy=greedy
        )

        if groups is None:
            offset = (stop_at + 1) if stop_at is not None else (offset + 1)
            continue

        for g_id, intervals in groups.items():
            all_groups.setdefault(g_id, []).extend(intervals)

        offset = end_index

    return all_groups
