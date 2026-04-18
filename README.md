<h1>
   <img src="images/pyre.png" alt="pyre logo" width="80" style="vertical-align: middle;">
   pyre — A Regular Expression Engine Based on Derivatives
</h1>

<div align="center" style="padding: 10px;">
  <img src="images/Regular Expressions.png" width="30%">
</div>
**pyre** is a Python implementation of a regular-expression engine built using
**Brzozowski derivatives**. Unlike traditional engines that first translate the
expression into an NFA and then to a DFA, a derivative-based engine constructs
the DFA directly from the expression by repeatedly applying derivative rules.
This also allows novel set operations like language complement (NOT) `~`,
intersection (AND) `&`, symmetric difference (XOR) `^`, and difference `-` in an
efficient manner. Because matching is performed on the resulting DFA, the
recognizer runs in linear time and does not require backtracking.

The project includes:

- A lexer and parser written in PLY
- A full AST of regular-expression operators
- DFA construction using derivatives
- Capture-group support
- `match()` and `search()` APIs
- Verbose patterns ala Python `re.X` with inline comments `#` allowed
- An example calculator app using lexer feature
- A command-line interface called `pyre`

---

## Background and References

1. **Implementing a More Powerful Regex (original 2013 blog post)**
  Andrew Kuhnhausen
   Available via the Internet Archive (Wayback Machine):
   [https://web.archive.org/web/20171223232901/http://blog.errstr.com/2013/01/22/implementing-a-more-powerful-regex/](https://web.archive.org/web/20171223232901/http://blog.errstr.com/2013/01/22/implementing-a-more-powerful-regex/)
2. **Regular-expression derivatives reexamined**
  Matthew Owens, John Reppy, Aaron Turon
   *Journal of Functional Programming*, Vol 19 Issue 2, March 2009
3. **Design and Implementation of a validating XML parser in Haskell**
  Master's Thesis — Martin Schmidt
   [https://www.fh-wedel.de/~si/HXmlToolbox/thesis/](https://www.fh-wedel.de/~si/HXmlToolbox/thesis/)
4. **Regular Expression Matching Can Be Simple And Fast (but is slow in Java, Perl, PHP, Python, Ruby, ...)**
  Russ Cox
   [https://swtch.com/~rsc/regexp/regexp1.html](https://swtch.com/~rsc/regexp/regexp1.html)
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

```bash
bash scripts/get_ply.sh
```

---

## Command Line Usage

```bash
pyre [-h] [--debug] [--no-greedy] [--all] regex [target]
```

Example:

```bash
pyre 'lex' test.cpp
```

---

## Python Usage

```python
#!/usr/bin/env python

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
result1 = pyre.match(compiled, "ac")
print(result1)  # {1: (0, 1), 0: (0, 2)}
result2 = pyre.match(compiled, "bc")
print(result2)  # {1: (0, 1), 0: (0, 2)}
```

---

## Pyre Uses Verbose Patterns

`Pyre` treats all patterns as verbose (similar to Python's `re.X` flag, but
always on).  Unescaped whitespace is ignored and `#` introduces a comment to end
of line. This encourages writing self-documenting patterns without any extra
flags:

The following showcases how useful language complement works.

```sh
pyre '/\*         # Comment start
      ~(          # Complement: strings NOT containing */
        .*        # Any prefix
        \*/       # The forbidden sequence
        .*        # Any suffix
      )           # End complement
      \*/         # Comment end' \
    `<file`>
```

Without complement, you'd have to use something like:

`'/\* ( [^*] | \*+ [^/] )* \*/'`

That has some serious `¯_(ツ)_/¯` vibes.

Use `\s` (backslash-space) or a character class to match a literal space.

---

## Example Application

In `examples` there's a `calc` program which shows how you can use the library to construct a lexer.

The most interesting bit is here:

```python
class Lexer:
    # Rule order is law out here: first match wins when two patterns can hit the same spot.
    _SPECS = [
        ('WS',        r"\s+"),
        ('NUMBER',    r"\d+\.\d*|\.\d+|\d+"),  # 123, 123.45, .45, 123.
        ('PLUS',      r"\+"),
        ('MINUS',     r"-"),
        ('TIMES',     r"\*"),
        ('DIVIDE',    r"/"),
        ('POWER',     r"\^"),
        ('FACTORIAL', r"!"),
        ('LPAREN',    r"\("),
        ('RPAREN',    r"\)"),
        ('OTHER',     r".")
    ]

    re_spec = "|".join(f"(?P<{kind}>{pat})" for kind, pat in _SPECS)
    _CALC_DFA = pyre.compile(re_spec)

    def __init__(self, text: str):
        self.text = text
        self.tokens = list(self._lex_tokens())
        self.pos = 0

    def _convert_number(self, s: str):
        return float(s) if "." in s else int(s)

    def _lex_tokens(self):
        for kind, token, start, end in self._CALC_DFA.lex(self.text):

            if kind == "WS":
                continue

            if kind == "NUMBER":
                value = self._convert_number(token)
            else:
                value = token

            yield Token(kind, value, token, start, end)

        eof = len(self.text)
        yield Token('EOF', '<EOF>', '', eof, eof)
```

The token types are assembled into a large alternation. Internally this is what lexers do when you give it a series of rules. You can perform the same operations using Python's `re` but this is slightly more compact.

---

## Powerful Set Operators

What if we wanted to test whether two REs recognize the same language?

```sh
pyre -d 'a(?:b|c) ^ (?:ab | ac)'
```

```
q0: DFAState(name=q0 regex=a·(b | c) ^ (a·b | a·c)) (events=set())
    [a] Goto(next=q1 events=set())
    [\x00-`b-ÿ] Goto(next=q1 events=set())
q1: DFAState(name=q1 regex=∅) (events=set())
    [\x00-ÿ] Goto(next=q1 events=set())
Total DFA states: 2
Total RE instances: 13
```

You can then iterate over the DFA and confirm it is either empty or has no accepting states.

---

## Project Structure

```
 ├── .gitignore
 ├── README.md
 ├── __init__.py
 ├── cli.py
 ├── dfa.py
 ├── event.py
 ├── examples
 │   ├── calc
 │   └── ccomment
 ├── images
 │   ├── Regular Expressions.png
 │   └── pyre.png
 ├── parser.py
 ├── pyre
 ├── regex.py
 ├── scripts
 │   └── get_ply.sh
 ├── test
 │   ├── __init__.py
 │   ├── test_basic.py
 │   ├── test_boolean.py
 │   ├── test_capture.py
 │   ├── test_common.py
 │   └── test_repeat.py
 └── util.py
```

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