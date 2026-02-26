"""
pyre - A Regular Expression Engine Based on Derivatives
"""

from .dfa import compile as _compile_dfa, DFA
from .parser import Parser


def compile(pattern):
    """
    Compile a regex pattern string into a DFA.
    """
    if isinstance(pattern, DFA):
        return pattern
    elif isinstance(pattern, str):
        parser = Parser()
        expr = parser.parse(pattern)
        if parser.errors:
            raise ValueError(f'Invalid regex pattern: {repr(pattern)}')
        return _compile_dfa(expr)

    raise TypeError(f"Unsupported pattern type: {type(pattern).__name__}")

def fullmatch(pattern, string):
    return compile(pattern).fullmatch(string)

def match(pattern, string):
    return compile(pattern).match(string)

def search(pattern, string, *, all=False, **kwargs):
    return compile(pattern).search(string, all=all, **kwargs)

__all__ = ['compile', 'match', 'fullmatch', 'search', 'Parser']
