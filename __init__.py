"""
pyre - A Regular Expression Engine Based on Derivatives
"""

from typing import Dict, Iterable, List, Tuple, Union

from .dfa import compile as _compile_dfa, lexer as _lexer_dfa, DFA, Token
from .regex import Regex
from . import parser as _parser
from .parser import PatternError

Pattern = Union[str, Regex, DFA]
Text = Union[str, bytes]
Span = Tuple[int, int]
MatchResult = Dict[Union[int, str], List[Span]]


def parse(pattern: str) -> Regex:
    """
    Parse a regex pattern string into a Regex AST node.
    Raises PatternError, a ValueError, if the pattern is invalid.
    """
    return _parser.parse(pattern)


def _to_regex(pattern: Pattern) -> Regex:
    if isinstance(pattern, str):
        return parse(pattern)
    if isinstance(pattern, Regex):
        return pattern
    if isinstance(pattern, DFA):
        return pattern.expr
    raise TypeError(f'expected str, Regex, or DFA, got {type(pattern).__name__}')


def compile(pattern: Pattern) -> DFA:
    """
    Compile a regex pattern string or Regex AST node into a DFA.
    Already-compiled DFAs are returned as-is.
    """
    if isinstance(pattern, DFA):
        return pattern
    return _compile_dfa(_to_regex(pattern))

def lexer(rules: Iterable[Tuple[str, Pattern]]) -> DFA:
    """
    Compile (name, pattern) rules into one DFA for DFA.lex(). Each token is
    named after the rule matching the longest text, the earliest rule on
    ties, and its groups are numbered within that rule's pattern.
    """
    rules = list(rules)
    if not rules:
        raise ValueError('lexer() needs at least one rule')
    return _lexer_dfa([name for name, _ in rules],
                      [_to_regex(pattern) for _, pattern in rules])

def fullmatch(pattern: Pattern, string: Text) -> MatchResult:
    return compile(pattern).fullmatch(string)

def match(pattern: Pattern, string: Text) -> MatchResult:
    return compile(pattern).match(string)

def search(pattern: Pattern, string: Text, *, all: bool = False, **kwargs) -> MatchResult:
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
    'lexer',
    'match',
    'fullmatch',
    'search',
    'isempty',
    'equal',
    'subset',
    'PatternError',
    'Token',
]
