#
# dfa.py
#

import logging
LOG = logging.getLogger(__file__)

import util
import regex

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


# Capture group object
#
class Group:
    def __init__(self, name, start, end):
        self.name = name
        self.start = start
        self.end = end

    def as_tuple(self):
        return (self.start, self.end)

    def __str__(self):
        return f'Group(name={self.name} {self.start}, {self.end})'

    def __repr__(self):
        return f'Group(name={self.name} {self.start}, {self.end})'


class GroupInfo:
    """
    Tracks capture groups based on the set of active groups from each DFA step.

    Mirrors the logic originally in `search()`:
      - safe copies of active keys before computing diffs
      - supports multiple groups
    """
    def __init__(self):
        self.active = {}   # g -> start_index
        self.final  = {}   # g -> Group object (or similar)

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
            # Use your Group class here
            self.final[g] = Group(g, start, index)
            del self.active[g]

        return started, ended

    def close(self, end_index):
        """
        Close any still-active groups at a final end position (exclusive),
        e.g. when overall match ends.
        """
        for g, start in list(self.active.items()):
            self.final[g] = Group(g, start, end_index)
            del self.active[g]


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
            {group_id: (start, end)}
        where start/end are 0-based indices into `string`, end-exclusive.
    """
    start_state = compile(expr)   # bare expr, no .* wrapping
    group_info = GroupInfo()
    state = start_state

    for step in dfa_run(start_state, string):
        state = step.state

        # Dead state → match impossible
        #
        if state.isempty:
            return {}

        # Track capture groups safely
        #
        group_info.step(step.index, step.group)

    # End of input: require accepting state for a full match
    #
    if not state.isnullable():
        return {}

    # Close any still-active groups at end-of-string
    #
    end_index = len(string)
    group_info.close(end_index)

    # If group 0 didn't get recorded via transitions, synthesize it
    #
    if 0 not in group_info.final:
        group_info.final[0] = Group(0, 0, end_index)

    # Expose simple intervals instead of Group objects
    #
    result = {g_id: grp.as_tuple() for g_id, grp in group_info.final.items()}
    return result


# Searching is a special case of matching, and we can take advantage of wildcard
# behavior of .* to find a pattern within a string. Rewrite our pattern
# surrounded by any match.
#
def search(expr, string, *, all=False):
    """
    Search for `expr` in `string`.

    If all is False (default):
        - returns {} if no match
        - otherwise returns {group_id: (start, end)} for the first match

    If all is True:
        - returns {} if no match
        - otherwise returns {group_id: [(start, end), ...]} where each
          (start, end) is one non-overlapping match for that group.
    """
    start_state = compile(expr)
    n = len(string)

    # First match
    #
    if not all:
        offset = 0

        while offset < n:
            state = start_state
            group_info = GroupInfo()

            for step in dfa_run(start_state, string, start_index=offset):
                state = step.state

                if state.isempty:
                    # This run died; restart at next character
                    offset = step.index + 1
                    break

                group_info.step(step.index, step.group)

                if state.isnullable():
                    # Found a match ending at end_index
                    end_index = step.index + 1
                    group_info.close(end_index)
                    return {
                        g_id: grp.as_tuple()
                        for g_id, grp in group_info.final.items()
                    }

            else:
                # Reached end of string without dead or accept for this offset
                return {}

        # Exhausted all offsets with no match
        return {}

    # All matches
    #
    all_groups = {}   # group_id -> [ (start, end), ... ]
    offset = 0

    while offset < n:
        state = start_state
        group_info = GroupInfo()
        made_progress = False

        for step in dfa_run(start_state, string, start_index=offset):
            state = step.state

            if state.isempty:
                # This run died; move offset forward and try again
                offset = step.index + 1
                made_progress = True
                break

            group_info.step(step.index, step.group)

            if state.isnullable():
                end_index = step.index + 1
                group_info.close(end_index)

                # Merge this match's groups into the accumulator
                for g_id, grp in group_info.final.items():
                    all_groups.setdefault(g_id, []).append(grp.as_tuple())

                # Non-overlapping: restart from end of this match
                offset = end_index
                made_progress = True
                break

        if not made_progress:
            # No dead state and no accept from this offset → nothing more to find
            break

    return all_groups
