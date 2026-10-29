#
# dfa.py
#

import functools
import logging
import operator
import weakref
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


class _Text:
    """
    Text as the DFA reads it. Patterns match code points, but the DFA steps
    through UTF-8 bytes, so data holds one byte per character of a str
    decoded as Latin-1, and each character indexes a 256-entry transition
    table. Offsets into data are byte offsets, and index() maps them back
    to offsets into the text given, a str or bytes. Only a str that is not
    all ASCII needs that; mapped says whether it does.
    """
    __slots__ = ('text', 'data', 'mapped', '_offsets')

    def __init__(self, text):
        self.text = text
        self.mapped = False
        self._offsets = None

        if isinstance(text, str):
            # ASCII is its own UTF-8
            #
            if text.isascii():
                self.data = text
            else:
                self.data = text.encode('utf-8', 'surrogatepass').decode('latin-1')
                self.mapped = True
        elif isinstance(text, (bytes, bytearray, memoryview)):
            self.data = bytes(text).decode('latin-1')
        else:
            raise TypeError(f'expected str or bytes, got {type(text).__name__}')

    def index(self, offset):
        """ The offset into text of the byte offset into data """
        if not self.mapped:
            return offset

        if self._offsets is None:
            offsets = [0] * (len(self.data) + 1)
            pos = 0
            for i, ch in enumerate(self.text):
                offsets[pos] = i
                pos += 1 if ch < '\x80' else 2 if ch < '\u0800' else 3 if ch < '\U00010000' else 4
            offsets[pos] = len(self.text)
            self._offsets = offsets

        return self._offsets[offset]

    def spans(self, groups):
        """ groups, as match() returns them, with offsets into text """
        if not self.mapped:
            return groups

        index = self.index
        return {gid: [(index(start), index(end)) for start, end in intervals]
                for gid, intervals in groups.items()}


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

            for mask in sorted(current.charset.masks):
                ranges = regex.mask_ranges(mask)
                char = chr(ranges[0][0])

                _next = DFAState(tuple(r.derive(char) for r in current.vector))

                LOG.debug('Derivative of %s of %r => %s', current.name, char, _next)
                LOG.debug('Transition for %s', regex.CharSet.fmt_mask(mask))

                goto = Goto(_next)

                for lo, hi in ranges:
                    for code in range(lo, hi + 1):
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
        Iterate over `text[index:]`, where text is as the DFA reads it: one
        byte per character (see _Text).

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

        text = _Text(text)
        data = text.data
        state = self.initial

        for step in self.run(data):
            state = step.state
            LOG.debug('Match: Step %s', step)

            # Dead state
            #
            if state.isdead:
                return {}

        if state.accept is None:
            return {}

        return text.spans(self._groups(data, 0, len(data), state.accept))


    def match(self, text, *, greedy=True):
        text = _Text(text)
        _, groups = self._run_from(text.data, 0, greedy=greedy)
        return text.spans(groups)


    def _run_from(self, text, offset, *, greedy=True, nonempty=False):
        """
        Run the DFA from offset to find the match end, then extract capture
        groups for that span.
        Returns (end_index, groups); (None, {}) if no match.
        """
        end, rule = self._end(text, offset, greedy=greedy, nonempty=nonempty)

        if end is None:
            return None, {}

        return end, self._groups(text, offset, end, rule)

    def _end(self, text, offset, *, greedy=True, nonempty=False):
        """
        Run the DFA from offset until it reaches the dead state. The match
        ends at the last accepting state, or the first if not greedy, and
        belongs to the rule that state accepts. An accepting initial state
        is an empty match at offset, unless nonempty.
        Returns (end_index, rule); (None, None) if no match.
        """
        state = self.initial
        end = rule = None

        if state.accept is not None and not nonempty:
            end, rule = offset, state.accept
            if not greedy:
                return end, rule

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

    # Skip to the next character boundary, past UTF-8 continuation bytes
    #
    @staticmethod
    def _boundary(s, offset):
        n = len(s)
        while offset < n and '\x80' <= s[offset] < '\xc0':
            offset += 1
        return offset

    def _find(self, data, offset, *, greedy=True, nonempty=False):
        """
        The leftmost match starting at offset or after, as
        (start, end, groups), or None. If nonempty, a match starting at
        offset itself can't be empty.

        A pattern that matches empty matches at every character boundary,
        the end of the text included, so only one that doesn't can skip
        ahead to where a match can begin.
        """
        n = len(data)
        empty = self.initial.accept is not None

        while offset <= n:
            if empty:
                offset = self._boundary(data, offset)
            else:
                offset = self._skip(data, offset)
                if offset >= n:
                    break
            end, groups = self._run_from(data, offset, greedy=greedy, nonempty=nonempty)
            if groups:
                return offset, end, groups
            nonempty = False
            offset += 1

        return None


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
        text = _Text(text)
        data = text.data

        if not all:
            found = self._find(data, 0, greedy=greedy)
            return text.spans(found[2]) if found else {}

        # As in Python's re, each search starts where the last match ended,
        # and after an empty match the next one can't be empty at the same
        # place, so the search always moves on
        #
        all_groups = {}
        offset = 0
        nonempty = False
        while True:
            found = self._find(data, offset, greedy=greedy, nonempty=nonempty)
            if found is None:
                break
            start, end, groups = found
            for gid, intervals in groups.items():
                all_groups.setdefault(gid, []).extend(intervals)
            offset, nonempty = end, start == end

        return text.spans(all_groups)


    def lex(self, text):
        """
        Split text into tokens, taking the longest match and the earliest
        rule on ties. Yields a Token for each, and raises LexError where
        nothing matches, after the tokens before it.

        A DFA built by lexer() names each token after the rule that matched,
        and runs the capture pass only if the token's groups are read. A
        single pattern names each token after the named group spanning it,
        which needs the capture pass on every token.
        """
        text = _Text(text)
        data = text.data
        index = 0
        while index < len(data):
            # A token can't be empty, or lexing would make no progress
            #
            end, rule = self._end(data, index, nonempty=True)

            if end is None:
                raise self._lex_error(text, index, 'no rule matches')

            if self.names:
                yield Token(self.names[rule], text, index, end, self, rule)
            else:
                groups = self._groups(data, index, end, rule)

                kind = None
                for gid, intervals in groups.items():
                    # Skip numbered groups since we want named ones, and
                    # only choose a match for the entire span
                    #
                    if not isinstance(gid, int) and (index, end) in intervals:
                        kind = gid

                if not kind:
                    raise self._lex_error(text, index, 'no named group spans the match of')

                yield Token(kind, text, index, end, self, rule, text.spans(groups))

            index = end

    @staticmethod
    def _lex_error(text, index, msg):
        pos = text.index(index)
        source = text.text
        if not isinstance(source, str):
            source = bytes(source)
        return LexError(f'{msg} {source[pos:pos + 1]!r}', source, pos)

    def isempty(self):
        """Returns True if the language of this DFA is empty (no reachable accepting states)."""
        return all(state.accept is None for state in self.states)


class LexError(ValueError):
    """
    Raised by DFA.lex() at text it can't split into tokens. Like
    PatternError, it carries the text and the position, which counts bytes
    in bytes text, with lineno and colno counted from 1.
    """
    def __init__(self, msg, text, pos):
        self.msg = msg
        self.text = text
        self.pos = pos
        self.lineno, self.colno = util.line_col(text, pos)

        message = f'{msg} at position {pos}'
        newline = '\n' if isinstance(text, str) else b'\n'
        if newline in text:
            message += f' (line {self.lineno}, column {self.colno})'

        super().__init__(message)


class Token:
    """
    A token from DFA.lex(). It unpacks like the tuple (kind, text, start,
    end), where text is the matched string, or bytes for bytes input.

    groups maps group numbers and names to spans, as match() does, and is
    computed the first time it is read.
    """
    __slots__ = ('kind', 'text', 'start', 'end', '_input', '_byte_start', '_byte_end',
                 '_dfa', '_rule', '_groups')

    def __init__(self, kind, source, start, end, dfa, rule, groups=None):
        """ source is the _Text lexed, and start and end are byte offsets """
        self._byte_start = start
        self._byte_end = end
        if source.mapped:
            start, end = source.index(start), source.index(end)

        self.kind = kind
        self.start = start
        self.end = end
        self.text = source.text[start:end]
        self._input = source
        self._dfa = dfa
        self._rule = rule
        self._groups = groups

    @property
    def groups(self):
        if self._groups is None:
            groups = self._dfa._groups(self._input.data, self._byte_start, self._byte_end, self._rule)
            self._groups = self._input.spans(groups)
        return self._groups

    def group(self, gid=0):
        """ The text of group gid, a number or name, or None if it did not match """
        intervals = self.groups.get(gid)
        if not intervals:
            return None
        start, end = intervals[0]
        return self._input.text[start:end]

    def __iter__(self):
        return iter((self.kind, self.text, self.start, self.end))

    def __getitem__(self, index):
        return (self.kind, self.text, self.start, self.end)[index]

    def __repr__(self):
        return f'Token({self.kind!r}, {self.text!r}, {self.start}, {self.end})'


class DFAState:
    # Held weakly, as Regex nodes are: a state lives while some DFA uses it
    #
    _instances = weakref.WeakValueDictionary()

    def __new__(cls, vector):
        try:
            return cls._instances[vector]
        except KeyError:
            pass

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
