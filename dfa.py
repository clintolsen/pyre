#
# dfa.py
#

import logging
LOG = logging.getLogger(__file__)

from . import util
from . import regex
from . import event
from .event import Event

from collections import namedtuple
DFAStep = namedtuple("DFAStep", "index char prev_state state goto")

# Manage state transition information. In addition to keeping track of the next
# state, we will also house info about which particular states were used to
# compute the transition, generally a RegexDot or RegexSym.
#
class Goto:
    def __init__(self, _next, _states=None):
        self._next = _next
        self._states = _states if _states is not None else set()
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
        return f'Goto(next={self._next.name} events={self.events})'

    def __repr__(self):
        return f'{self}'


class DFA:
    def __init__(self, expr):
        self.states = set()
        self.initial = DFAState(expr)

        todo = {self.initial}

        while todo:
            current = todo.pop()
            self.states.add(current)
            current.name = f'q{len(self.states)}'

            LOG.debug(f'Current state {current.name}: {current}')

            markers = current.regex.prefix_markers()
            events = set()
            for marker in markers:
                events |= set(marker.events)

            current.prefix_events = events

            classes = current.regex.charset.get_int_sets()

            for charset in classes:
                if charset:
                    char = chr(charset[0][0])

                    accept = set()
                    _next = DFAState(current.regex.derive(char, accept))

                    LOG.debug(f'Derivative of {current.name} of {repr(char)} => {_next}')
                    LOG.debug(f'Transition for {[regex.CharSet._fmt_char(x) for x in charset[0]]} is {accept}')

                    goto = Goto(_next, accept)

                    LOG.debug(f'Goto events: {goto.events}')

                    for rng in charset:
                        for code in range(rng[0], rng[-1] + 1):
                            current.goto[code] = goto

                    if _next not in self.states:
                        todo.add(_next)

        self.states.add(DFAState.empty())
        DFAState.empty().name = f'q{len(self.states)}'

        if LOG.getEffectiveLevel() == logging.DEBUG:
            for state in sorted(self.states, key=lambda x: x.name):
                label = state.name
    
                if state.regex.isnullable():
                    label = util.highlight(label)
    
                print(f'{label}: {state} (events={state.prefix_events})')
    
                classes = state.regex.charset.get_int_sets()
    
                for charset in classes:
                    if charset:
                       goto = state.goto[charset[0][0]]
                       inside = regex.CharSet.fmt_ranges(charset)
                       print(f"    [{inside}] {goto}")
    
        LOG.debug('Total DFA states: %d' % len(self.states))
        LOG.debug('Total RE instances: %d' % len(regex.Regex._instance))


    def run(self, text, index=0):
        """
        Iterate over `text[index:]`.
    
        Yields DFAStep(index, char, prev_state, state, goto)
        where:
          - prev_state: state before reading char
          - state:      state after reading char
          - goto:       the Goto object used
        """
        state = self.initial
        for i in range(index, len(text)):
            ch = text[i]
            goto = state.goto[ord(ch)]
            _next = goto._next

            yield DFAStep(
                index=i,
                char=ch,
                prev_state=state,
                state=_next,
                goto=goto,
            )
            state = _next
    

    def fullmatch(self, text):
        """
        Full-string match against `text`.
    
        Returns:
            {} if no match
    
            Otherwise:
                {group_id: [(start, end), ...]}
            where start/end are 0-based indices into `text`, end-exclusive.
        """
        group_info = GroupInfo()
    
        LOG.debug(f'Match: {self.initial} against {text}')
    
        state = self.initial
    
        for step in self.run(text):
            state = step.state
            LOG.debug(f'Match: Step {step}')
    
            # Dead state
            #
            if state.regex.isempty:
                return {}
    
            # Track capture groups
            group_info.step(step.index, step.goto.events)
    
        if not state.regex.isnullable():
            return {}
    
        end_index = len(text)
    
        # Finalize match span [0, end_index) and guarantee group 0 exists
        #
        finalized = group_info.finalize(0, end_index)
    
        return finalized

    def match(self, text, *, greedy=True):
        end_index = self._span_from(text, 0, greedy=greedy)
        if end_index is None:
            return {}
        return self._match_to_end(text, 0, end_index)


    # Skip over known bad start characters
    #
    def _skip(self, s, offset):
        n = len(s)
        while offset < n and self.initial.goto[ord(s[offset])]._next.regex.isempty:
            offset += 1
        return offset

    def search(self, text, *, greedy=True, all=False):
        """
        Search in `text`.
    
        Greedy: Find the longest match.
    
        If all is False (default):
            - returns {} if no match
            - otherwise returns {group_id: [(start, end)]} for the first match
    
        If all is True:
            - returns {} if no match
            - otherwise returns {group_id: [(start, end), ...]} where each
              (start, end) is one non-overlapping match for that group.
        """
        n = len(text)
    
        if not all:
            offset = self._skip(text, 0)
            while offset < n:
                end_index = self._span_from(text, offset, greedy=greedy)
    
                if end_index is not None:
                    return self._match_to_end(text, offset, end_index)
    
                offset = self._skip(text, offset + 1)
    
            return {}

        all_groups = {}
        offset = self._skip(text, 0)
    
        while offset < n:
            end_index = self._span_from(text, offset, greedy=greedy)
    
            if end_index is None:
                offset = self._skip(text, offset + 1)
                continue
    
            groups = self._match_to_end(text, offset, end_index)
    
            for gid, intervals in groups.items():
                all_groups.setdefault(gid, []).extend(intervals)
    
            offset = self._skip(text, end_index)
    
        return all_groups

    def _span_from(self, text, offset, *, greedy=True):
        """
        Return the best end index (exclusive) of a match starting at offset,
        or None if no match.
        """
        latest_end = None
    
        for step in self.run(text, index=offset):
            state = step.state
    
            if state.regex.isempty:
                return latest_end
    
            if state.regex.isnullable():
                latest_end = step.index + 1
                if not greedy:
                    return latest_end
    
        return latest_end
    

    def _match_to_end(self, text, offset, end_index):
        """
        Run DFA from offset up to end_index and compute capture groups.
        """
        group_info = GroupInfo()
        last_state = self.initial
    
        for step in self.run(text, index=offset):
            if step.index >= end_index:
                break
    
            state = step.state
            if state.regex.isempty:
                break
    
            group_info.step(step.index, step.goto.events)
            last_state = state
    
        # apply boundary CLOSE events at the match endpoint
        close_events = {e for e in last_state.prefix_events if e.kind == event.CLOSE}
        if close_events:
            group_info.step(end_index, close_events)
    
        return group_info.finalize(offset, end_index)


class DFAState:
    _empty = None
    _instances = {}

    def __new__(cls, expr):
        if expr in cls._instances:
            return cls._instances[expr]

        self = object.__new__(cls)
        cls._instances[expr] = self

        self.regex = expr
        self.name = None
        self.prefix_events = None
        self.goto = [Goto(DFAState.empty(), None)] * 256

        return self

    @classmethod
    def empty(cls):
        if cls._empty is None:
            cls._empty = object.__new__(cls)
            cls._empty.regex = regex.RegexEmpty()
            cls._empty.name = None
            cls._empty.prefix_events = None
            cls._empty.goto = [Goto(cls._empty)] * 256
            cls._instances[cls._empty.regex] = cls._empty

        return cls._empty

    __hash__ = object.__hash__

    def __eq__(self, other):
        return self is other

    def __repr__(self):
        return f'DFAState(name={self.name} regex={self.regex})'

def compile(expr):
    ''' Construct a DFA from a regular expression '''
     
    dfa = DFA(expr)
    return dfa

class GroupInfo:
    """
    Tracks capture groups based on the set of active groups from each DFA step.
    """
    def __init__(self):
        self.active = {}   # g -> start_index
        self.final  = {}   # g -> [(start, end), ...]
        self.names  = {}   # g -> name (str)

    def step(self, index: int, events: set[Event]):
        """
        index  = current character index in the input (same `index` you log in DFAStep)
        events = set of Event(...) from the transition (goto.events)
        """
        if not events:
            return 

        # Handle close events first 
        # 
        closes = [e for e in events if e.kind == event.CLOSE]
        opens  = [e for e in events if e.kind == event.OPEN]

        for e in closes:
            gid = e.gid
            if gid in self.active:
                start = self.active[gid]
                self.final.setdefault(gid, []).append((start, index))
                del self.active[gid]

        for e in opens:
            # Named groups
            #
            if e.name:
                self.names[e.gid] = e.name

            gid = e.gid
            # If you can get nested or repeated OPEN without CLOSE, decide policy.
            # For now: overwrite start (or ignore if already open).
            #
            self.active[gid] = index


    def finalize(self, match_start: int, match_end: int):
        out = {g: list(v) for g, v in self.final.items()}

        # Close any still-active groups at end of match
        #
        for gid, start in self.active.items():
            out.setdefault(gid, []).append((start, match_end))

        # Whole match
        #
        out.setdefault(0, []).append((match_start, match_end))

        # Add named groups
        #
        named = {
            name: out[gid]
            for gid, name in self.names.items()
            if gid in out
        }

        # Shouldn't collide
        #
        out = {**named, **out}

        return out
