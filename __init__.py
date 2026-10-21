"""
pyre - A Regular Expression Engine Based on Derivatives
"""

from typing import Dict, List, Tuple, Union

from .dfa import compile as _compile_dfa, DFA
from .regex import Regex
from .parser import Parser

Pattern = Union[str, Regex, DFA]
Span = Tuple[int, int]
MatchResult = Dict[Union[int, str], List[Span]]


def parse(pattern: str) -> Regex:
    """
    Parse a regex pattern string into a Regex AST node.
    """
    parser = Parser()
    expr = parser.parse(pattern)
    if parser.errors or expr is None:
        raise ValueError(f'Invalid regex pattern: {repr(pattern)}')
    return expr


def _to_regex(pattern: Pattern) -> Regex:
    if isinstance(pattern, str):
        return parse(pattern)
    if isinstance(pattern, Regex):
        return pattern
    if isinstance(pattern, DFA):
        return pattern.initial.regex
    raise TypeError(f'expected str, Regex, or DFA, got {type(pattern).__name__}')


def compile(pattern: Pattern) -> DFA:
    """
    Compile a regex pattern string or Regex AST node into a DFA.
    Already-compiled DFAs are returned as-is.
    """
    if isinstance(pattern, DFA):
        return pattern
    return _compile_dfa(_to_regex(pattern))

def fullmatch(pattern: Pattern, string: str) -> MatchResult:
    return compile(pattern).fullmatch(string)

def match(pattern: Pattern, string: str) -> MatchResult:
    return compile(pattern).match(string)

def search(pattern: Pattern, string: str, *, all: bool = False, **kwargs) -> MatchResult:
    return compile(pattern).search(string, all=all, **kwargs)

def isempty(pattern: Pattern) -> bool:
    return compile(pattern).isempty()

def _without_captures(pattern: Pattern) -> Regex:
    return _to_regex(pattern)._without_captures()

def equal(a: Pattern, b: Pattern) -> bool:
    return _compile_dfa(_without_captures(a) ^ _without_captures(b)).isempty()

def subset(a: Pattern, b: Pattern) -> bool:
    return _compile_dfa(_without_captures(a) - _without_captures(b)).isempty()

__all__ = [
    'parse',
    'compile',
    'match',
    'fullmatch',
    'search',
    'isempty',
    'equal',
    'subset',
    'Parser',
]
