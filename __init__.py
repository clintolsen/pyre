"""
pyre - A Regular Expression Engine Based on Derivatives
"""

from .dfa import compile as _compile_dfa, match as _match, search as _search
from .parser import Parser
from . import regex as _regex  # needed for isinstance checks


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

    # yo, if it's already compiled, don't recompile it
    if hasattr(pattern, "goto"):
        return pattern

    # if it's a raw AST node (Regex) with no goto yet, compile it
    if isinstance(pattern, _regex.Regex):
        return _compile_dfa(pattern)

    raise TypeError(f"Unsupported pattern type: {type(pattern).__name__}")


def _ensure_compiled(pattern):
    # ayyy same rules: strings get parsed, Regex nodes get compiled, compiled nodes pass thru
    return compile(pattern)


def match(pattern, string):
    compiled = _ensure_compiled(pattern)
    return _match(compiled, string)


def search(pattern, string, *, all=False, **kwargs):
    compiled = _ensure_compiled(pattern)
    return _search(compiled, string, all=all, **kwargs)


__all__ = ['compile', 'match', 'search', 'Parser']
