"""
pyre - A Regular Expression Engine Based on Derivatives
"""

from .dfa import compile as _compile_dfa, match as _match, fullmatch as _fullmatch, search as _search
from .parser import Parser
from . import regex as _regex


def compile(pattern):
    """
    Compile a regex pattern string into a DFA-ish start state.
    """
    if isinstance(pattern, str):
        parser = Parser()
        expr = parser.parse(pattern)
        if parser.errors:
            raise ValueError(f"Invalid regex pattern: {pattern}")
        return _compile_dfa(expr)
    elif isinstance(pattern, _regex.Regex):
        # Don't recompile
        #
        if hasattr(pattern, "goto"):
            return pattern

        return _compile_dfa(pattern)

    raise TypeError(f"Unsupported pattern type: {type(pattern).__name__}")


def _ensure_compiled(pattern):
    return compile(pattern)

def fullmatch(pattern, string):
    compiled = _ensure_compiled(pattern)
    return _fullmatch(compiled, string)

def match(pattern, string):
    compiled = _ensure_compiled(pattern)
    return _match(compiled, string)


def search(pattern, string, *, all=False, **kwargs):
    compiled = _ensure_compiled(pattern)
    return _search(compiled, string, all=all, **kwargs)


__all__ = ['compile', 'match', 'fullmatch', 'search', 'Parser']
