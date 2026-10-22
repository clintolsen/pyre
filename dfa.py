#
# dfa.py
#

import functools
import logging
import operator
LOG = logging.getLogger(__file__)

from . import util
from . import regex
from . import capture

from collections import namedtuple
DFAStep = namedtuple("DFAStep", "index char prev_state state goto")

# A DFA transition: the state reached on a character. Capture groups are not
# tracked here; a DFA state merges every live branch, so a transition cannot
# say which branch crossed a marker. See capture.py.
#
class Goto:
    def __init__(self, _next):
        self._next = _next

    def __str__(self):
        return f'Goto(next={self._next.name})'

    def __repr__(self):
        return f'{self}'


class DFA:
    def __init__(self, *exprs, names=None):
        # A state is a vector holding one derivative per expression, so it
        # tracks every rule at once and knows which ones still match. A
        # single pattern is a vector of one. Owens, Reppy and Turon call
        # these regular vectors.
        #
        # The DFA only decides whether text matches, where a match ends and
        # which rule it belongs to, which capture markers never affect, so
        # it is built from the expressions with captures stripped. That keeps
        # it smaller, and lets alternatives intern commutatively. The capture
        # pass runs on the original expression of the rule that matched,
        # where operand order sets group numbering and branch priority.
        #
        self.exprs = exprs
        self.names = names
        if LOG.isEnabledFor(logging.DEBUG):
            for i, expr in enumerate(exprs):
                label = f' {names[i]}' if names else ''
                LOG.debug('Pattern%s:\n%s', label, expr.tree())

        self.group_numbers = [capture.group_numbers(expr) for expr in exprs]
        self.states = set()
        self.initial = DFAState(tuple(expr._without_captures() for expr in exprs))

        todo = {self.initial}

        while todo:
            current = todo.pop()
            current.name = f'q{len(self.states)}'
            self.states.add(current)

            LOG.debug('Current state %s: %s', current.name, current)

            classes = current.charset.get_int_sets()

            for charset in classes:
                if charset:
                    char = chr(charset[0][0])

                    _next = DFAState(tuple(r.derive(char) for r in current.vector))

                    LOG.debug('Derivative of %s of %r => %s', current.name, char, _next)
                    LOG.debug('Transition for %s', [regex.CharSet._fmt_char(x) for x in charset[0]])

                    goto = Goto(_next)

                    for rng in charset:
                        for code in range(rng[0], rng[-1] + 1):
                            current.goto[code] = goto

                    if _next not in self.states:
                        todo.add(_next)

        dead = DFAState.dead(len(exprs))
        self.states.add(dead)
        if dead.name is None:
            dead.name = f'q{len(self.states)}'

        if LOG.getEffectiveLevel() == logging.DEBUG:
            for state in sorted(self.states, key=lambda x: x.name):
                label = state.name

                if state.accept is not None:
                    label = util.highlight(label)

                print(f'{label}: {state}')

                for mask in sorted(state.charset.masks):
                    lsb_pos = (mask & -mask).bit_length() - 1
                    goto = state.goto[lsb_pos]
                    print(f"    {regex.CharSet.fmt_mask(mask)} {goto}")

        LOG.debug('Total DFA states: %d', len(self.states))
        LOG.debug('Total RE instances: %d', len(regex.Regex._instance))

    @property
    def expr(self):
        """ One expression for the language the DFA accepts: any of its rules """
        return functools.reduce(regex.RegexOr, self.exprs)

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
        LOG.debug('Match: %s against %s', self.initial, text)

        state = self.initial

        for step in self.run(text):
            state = step.state
            LOG.debug('Match: Step %s', step)

            # Dead state
            #
            if state.isdead:
                return {}

        if state.accept is None:
            return {}

        return self._groups(text, 0, len(text), state.accept)


    def match(self, text, *, greedy=True):
        _, groups = self._run_from(text, 0, greedy=greedy)
        return groups


    def _run_from(self, text, offset, *, greedy=True):
        """
        Run the DFA from offset to find the match end, then extract capture
        groups for that span.
        Returns (end_index, groups); (None, {}) if no match.
        """
        end, rule = self._end(text, offset, greedy=greedy)

        if end is None:
            return None, {}

        return end, self._groups(text, offset, end, rule)

    def _end(self, text, offset, *, greedy=True):
        """
        Run the DFA from offset until it reaches the dead state. The match
        ends at the last accepting state, or the first if not greedy, and
        belongs to the rule that state accepts.
        Returns (end_index, rule); (None, None) if no match.
        """
        state = self.initial
        end = rule = None

        for index in range(offset, len(text)):
            state = state.goto[ord(text[index])]._next

            if state.isdead:
                break

            if state.accept is not None:
                end, rule = index + 1, state.accept
                if not greedy:
                    break

        return end, rule

    def _groups(self, text, start, end, rule):
        """
        Capture groups for the DFA-confirmed match text[start:end] of rule,
        taken from the single highest-priority accepting path.
        """
        numbers = self.group_numbers[rule]
        if not numbers:
            return {0: [(start, end)]}

        return capture.captures(self.exprs[rule], text, start, end, numbers)

    # Skip over known bad start characters
    #
    def _skip(self, s, offset):
        n = len(s)
        while offset < n and self.initial.goto[ord(s[offset])]._next.isdead:
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
        offset = 0

        if not all:
            while offset < n:
                offset = self._skip(text, offset)
                if offset >= n:
                    break
                end_index, groups = self._run_from(text, offset, greedy=greedy)
                if groups:
                    return groups
                offset += 1
            return {}

        all_groups = {}
        while offset < n:
            offset = self._skip(text, offset)
            if offset >= n:
                break
            end_index, groups = self._run_from(text, offset, greedy=greedy)
            if not groups:
                offset += 1
                continue
            for gid, intervals in groups.items():
                all_groups.setdefault(gid, []).extend(intervals)
            offset = end_index

        return all_groups


    def lex(self, text):
        """
        Split text into tokens, taking the longest match and the earliest
        rule on ties. Yields a Token for each, and stops where nothing
        matches.

        A DFA built by lexer() names each token after the rule that matched,
        and runs the capture pass only if the token's groups are read. A
        single pattern names each token after the named group spanning it,
        which needs the capture pass on every token.
        """
        index = 0
        while index < len(text):
            end, rule = self._end(text, index)

            if end is None:
                break

            if self.names:
                yield Token(self.names[rule], text, index, end, self, rule)
            else:
                groups = self._groups(text, index, end, rule)

                kind = None
                for gid, intervals in groups.items():
                    # Skip numbered groups since we want named ones, and
                    # only choose a match for the entire span
                    #
                    if not isinstance(gid, int) and (index, end) in intervals:
                        kind = gid

                if not kind:
                    break

                yield Token(kind, text, index, end, self, rule, groups)

            index = end

    def isempty(self):
        """Returns True if the language of this DFA is empty (no reachable accepting states)."""
        return all(state.accept is None for state in self.states)


class Token:
    """
    A token from DFA.lex(). It unpacks like the tuple (kind, text, start,
    end), where text is the matched string.

    groups maps group numbers and names to spans, as match() does, and is
    computed the first time it is read.
    """
    __slots__ = ('kind', 'text', 'start', 'end', '_source', '_dfa', '_rule', '_groups')

    def __init__(self, kind, source, start, end, dfa, rule, groups=None):
        self.kind = kind
        self.text = source[start:end]
        self.start = start
        self.end = end
        self._source = source
        self._dfa = dfa
        self._rule = rule
        self._groups = groups

    @property
    def groups(self):
        if self._groups is None:
            self._groups = self._dfa._groups(self._source, self.start, self.end, self._rule)
        return self._groups

    def group(self, gid=0):
        """ The text of group gid, a number or name, or None if it did not match """
        intervals = self.groups.get(gid)
        if not intervals:
            return None
        start, end = intervals[0]
        return self._source[start:end]

    def __iter__(self):
        return iter((self.kind, self.text, self.start, self.end))

    def __getitem__(self, index):
        return (self.kind, self.text, self.start, self.end)[index]

    def __repr__(self):
        return f'Token({self.kind!r}, {self.text!r}, {self.start}, {self.end})'


class DFAState:
    _instances = {}

    def __new__(cls, vector):
        if vector in cls._instances:
            return cls._instances[vector]

        self = object.__new__(cls)
        cls._instances[vector] = self

        self.vector = vector
        self.name = None

        # The rule the state accepts is the first one that matches here,
        # and the dead state is where every rule has failed.
        #
        self.accept = next((i for i, r in enumerate(vector) if r.isnullable()), None)
        self.isdead = all(r.isempty for r in vector)

        # Characters split the vector only where they split some component,
        # so its classes are where all of theirs meet.
        #
        self.charset = functools.reduce(operator.and_, (r.charset for r in vector))

        dead = self if self.isdead else DFAState.dead(len(vector))
        self.goto = [Goto(dead)] * 256

        return self

    @classmethod
    def dead(cls, n):
        return cls((regex.RegexEmpty(),) * n)

    __hash__ = object.__hash__

    def __eq__(self, other):
        return self is other

    def __repr__(self):
        if len(self.vector) == 1:
            shown = self.vector[0]
        else:
            shown = '(' + ', '.join(map(str, self.vector)) + ')'
        return f'DFAState(name={self.name} regex={shown})'

def compile(expr):
    ''' Construct a DFA from a regular expression '''
    return DFA(expr)

def lexer(names, exprs):
    ''' Construct a DFA whose rules are exprs, named by names '''
    return DFA(*exprs, names=names)
