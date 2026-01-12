# pyre — A Regular Expression Engine Based on Derivatives

**pyre** is a Python implementation of a regular-expression engine built using
**Brzozowski derivatives**. Unlike traditional engines that first translate the
expression into an NFA and then to a DFA, a derivative-based engine constructs
the DFA directly from the expression by repeatedly applying derivative rules.
This also allows novel set operations like language complement `(~RE)` and
intersection `(RE & RE)` in an efficient manner. Because matching is performed
on the resulting DFA, recognition runs in linear time and does not require
backtracking.

The project includes:

- A lexer and parser (PLY-based)
- A full AST of regular-expression operators
- DFA construction using derivatives
- Capture-group support
- `match()` and `search()` APIs
- A command-line interface called **`pyre`**

---

## Background and References

1. **Implementing a More Powerful Regex (original 2013 blog post)**
   Andrew Kuhnhausen 
   Available via the Internet Archive (Wayback Machine):
   https://web.archive.org/web/20171223232901/http://blog.errstr.com/2013/01/22/implementing-a-more-powerful-regex/

2. **Regular-expression derivatives reexamined**  
   Matthew Owens, John Reppy, Aaron Turon  
   *Journal of Functional Programming*, Vol 19 Issue 2, March 2009  

3. **Design and Implementation of a validating XML parser in Haskell**  
   Master's Thesis — Martin Schmidt  
   https://www.fh-wedel.de/~si/HXmlToolbox/thesis/

4. **Regular Expression Matching Can Be Simple And Fast (but is slow in Java, Perl, PHP, Python, Ruby, ...)**
   Russ Cox  
   https://swtch.com/~rsc/regexp/regexp1.html

5. **Janusz A. Brzozowski (1964)**  
   *Derivatives of Regular Expressions*  
   Journal of the ACM 11: 481–494  

---

## Installation

Requires **Python 3.8+** and **PLY**.

### Installing PLY

This project uses [PLY](https://www.dabeaz.com/ply/) (Python Lex–Yacc).
PLY is no longer actively distributed via PyPI, so it is not installed as a
package dependency. Instead, this project expects a local `ply/` directory
containing the PLY sources.

You can fetch a pinned version of PLY into `ply/` by running:

    bash scripts/get_ply.sh

---

## Command Line Usage

    pyre [-h] [--debug] regex target

Example:

    pyre 'lex' test.cpp

---

## Python Usage

  ```python
  import pyre
  
  # Simple API - pass pattern strings directly
  # Group 0 = full match, Group 1 = first capture group (a|b)
  #
  result = pyre.match("(a|b)c", "ac")
  print(result)  # {1: (0, 1), 0: (0, 2)}
  
  results = pyre.search("(a|b)c", "xxbcxx", all=True)
  print(results)  # {1: [(2, 3)], 0: [(2, 4)]}
  
  # Or compile once, use many times (for performance)
  #
  compiled = pyre.compile("(a|b)c")
  result1 = pyre.dfa.match(compiled, "ac")
  print(result1)  # {1: (0, 1), 0: (0, 2)}
  result2 = pyre.dfa.match(compiled, "bc")
  print(result2)  # {1: (0, 1), 0: (0, 2)}
  ```

---

## Project Structure

    pyre/
      __init__.py
      cli.py
      dfa.py
      parser.py
      pyre
      regex.py
      util.py
      test/
        __init__.py
        test_basic.py

---

## License

MIT License

Copyright (c) 2017-2026 Clint Olsen

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

---

## Acknowledgements

Thanks to **Russ Cox** ([swtch.com](https://swtch.com)) for his writing on
regular-expressions, finite automata, and his personal comments which encouraged me to
explore a derivative-based implementation.
