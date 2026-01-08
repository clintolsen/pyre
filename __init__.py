"""
pyre - A Regular Expression Engine Based on Derivatives
"""

from .dfa import compile as _compile_dfa, match as _match, search as _search
from .parser import Parser


def compile(pattern):
    """
    Compile a regex pattern string into a DFA.
    
    Args:
        pattern: A regex pattern string
        
    Returns:
        A compiled DFA state (regex expression object)
        
    Raises:
        ValueError: If the pattern is invalid
    """
    parser = Parser()
    expr = parser.parse(pattern)
    if parser.errors:
        raise ValueError(f"Invalid regex pattern: {pattern}")
    return _compile_dfa(expr)


def match(pattern, string):
    """
    Match a pattern against the entire string.
    
    Args:
        pattern: A regex pattern string
        string: The string to match against
        
    Returns:
        {} if no match, otherwise {group_id: (start, end)} for capture groups
    """
    parser = Parser()
    expr = parser.parse(pattern)
    if parser.errors:
        raise ValueError(f"Invalid regex pattern: {pattern}")
    compiled = _compile_dfa(expr)
    return _match(compiled, string)


def search(pattern, string, *, all=False):
    """
    Search for a pattern in a string.
    
    Args:
        pattern: A regex pattern string
        string: The string to search in
        all: If True, return all non-overlapping matches (default: False)
        
    Returns:
        {} if no match, otherwise:
        - If all=False: {group_id: (start, end)} for the first match
        - If all=True: {group_id: [(start, end), ...]} for all matches
    """
    parser = Parser()
    expr = parser.parse(pattern)
    if parser.errors:
        raise ValueError(f"Invalid regex pattern: {pattern}")
    compiled = _compile_dfa(expr)
    return _search(compiled, string, all=all)


__all__ = ['compile', 'match', 'search', 'Parser']