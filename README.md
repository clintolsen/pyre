<h1>
   <img src="images/pyre.png" alt="pyre logo" width="80" style="vertical-align: middle;">
   pyre — A Regular Expression Engine Based on Derivatives
</h1>

<div align="center" style="padding: 10px;">
  <img src="images/Regular Expressions.png" width="30%">
</div>

**Pyre** is a Python implementation of a regular-expression engine built using
**Brzozowski derivatives**. Unlike traditional engines that first translate the
expression into an NFA and then to a DFA, a derivative-based engine constructs
the DFA directly from the expression by repeatedly applying derivative rules.
This also allows novel set operations like language complement (NOT) `~`,
intersection (AND) `&`, symmetric difference (XOR) `^`, and difference `-` in an
efficient manner. Because matching is performed on the resulting DFA, the
recognizer runs in linear time and does not require backtracking. Capture groups
come from a second pass over the matched text that follows the pattern's partial
derivatives in Pike VM style, so it never backtracks either.

The project includes:

- A hand-written Pratt parser with no dependencies outside the standard library
- A full AST of regular-expression operators
- DFA construction using derivatives
- Capture groups, including named groups
- `match()`, `fullmatch()` and `search()` APIs, plus `lexer()` for flex-style tokenizing
- Set operators on parsed patterns, and `equal()`, `subset()` and `isempty()` language checks
- Verbose patterns ala Python `re.X` with inline comments `#` allowed
- Unicode patterns, matched against `str` or UTF-8 `bytes`
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
6. **Partial Derivatives of Regular Expressions and Finite Automaton Constructions**
  Valentin Antimirov
   *Theoretical Computer Science*, Vol 155 Issue 2, 1996, pp. 291–319
7. **Regular Expression Matching: the Virtual Machine Approach**
  Russ Cox
   [https://swtch.com/~rsc/regexp/regexp2.html](https://swtch.com/~rsc/regexp/regexp2.html)

---

## Installation

Requires **Python 3.9+**. There are no other dependencies.

---

## Command Line Usage

```bash
pyre [-h] [--debug] [--no-greedy] [--all] regex [target]
```

Example:

```bash
pyre 'lex' test.cpp
```

With a file, `pyre` prints it with every match highlighted. The file is read
and printed as bytes, so it needn't be valid UTF-8; bytes that aren't are
printed as they are and never match. Otherwise `target` is a string, and `pyre`
prints the groups of a full match against it. Like
`grep`, it exits with 0 if the pattern matched, 1 if it did not, and 2 for an
error such as a bad pattern.

---

## Python Usage

```python
#!/usr/bin/env python

import pyre

# Simple API - pass pattern strings directly
# Group 0 = full match, Group 1 = first capture group (a|b)
#
result = pyre.match("(a|b)c", "ac")
print(result)  # {1: [(0, 1)], 0: [(0, 2)]}

results = pyre.search("(a|b)c", "xxbcxx", all=True)
print(results)  # {1: [(2, 3)], 0: [(2, 4)]}

# Or compile once, use many times (for performance)
#
compiled = pyre.compile("(a|b)c")
result1 = pyre.match(compiled, "ac")
print(result1)  # {1: [(0, 1)], 0: [(0, 2)]}
result2 = pyre.match(compiled, "bc")
print(result2)  # {1: [(0, 1)], 0: [(0, 2)]}

# Parse when you want to compose, then compile once you are ready to match.
# See "Powerful Set Operators" below for predicates.
#
a = pyre.parse("a(?:b|c)")
b = pyre.parse("ab|ac")

union        = pyre.compile(a | b)
intersection = pyre.compile(a & b)
xor          = pyre.compile(a ^ b)
difference   = pyre.compile(a - b)
complement   = pyre.compile(~a)
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
    <file>
```

Without complement, you'd have to use something like:

`'/\* ( [^*] | \*+ [^*/] )* \*+ /'`

`pyre.equal()` confirms the two patterns match exactly the same comments.

That has some serious `¯\_(ツ)_/¯` vibes.

Use `\ ` (backslash-space) or `[ ]` to match a literal space, or `\s` for any
whitespace character. As in Python's `re.X`, whitespace inside a character class
is significant, and escapes such as `\t`, `\]` and `\d` work there too.

---

## Unicode

Patterns match characters, so `.`, `[α-ω]` and `→` each match one character
however many bytes it takes in UTF-8. Text can be a `str` or `bytes`:

```python
pyre.search("[α-ω]+", "x = λογος")          # {0: [(4, 9)]}
pyre.search("[α-ω]+", "x = λογος".encode())  # {0: [(4, 14)]}
```

Spans count characters in a `str` and bytes in `bytes`. Bytes that aren't valid
UTF-8 never match, and `.` matches any character, newline included. Lone
surrogates count as characters, as they do in Python's `re`, so a filename
decoded with `surrogateescape` still matches. `\d`, `\w` and `\s` are ASCII
only, like `re.ASCII`.

As in Python's `re`, `\xhh`, `\uhhhh` and `\Uhhhhhhhh` name a character by its
code point, with exactly 2, 4 or 8 hex digits, so `[\u03b1-\u03c9]` is `[α-ω]`.
A printed pattern writes characters that aren't printable this way. `\N{name}`
names one by its Unicode name instead, as in `\N{EM DASH}`.

The complement `~r` matches the text that `r` doesn't, so it only ever matches
whole characters too.

Internally the DFA reads UTF-8 one byte at a time, so its transition tables
stay 256 entries wide. A character class derives by a byte to the rest of each
character that byte can start, which builds the UTF-8 automaton on demand.

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

    _CALC_DFA = pyre.lexer(_SPECS)

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

`pyre.lexer()` compiles the rules into one DFA whose states track every rule at once, so each state knows which rule it accepts. Like flex, `lex()` takes the longest match, and the earliest rule when two match the same text.

Each token also carries the capture groups of the rule that matched, numbered within that rule's pattern, so there's no need to reparse the token text to pull it apart. They're only computed when you read them:

```python
lexer = pyre.lexer([
    ('NUMBER', r"(?P<int>\d+)(?:\.(?P<frac>\d+))?"),
    ('WS',     r"\s+"),
])

for token in lexer.lex("3.14 42"):
    print(token, token.group('int'), token.group('frac'))
```

```
Token('NUMBER', '3.14', 0, 4) 3 14
Token('WS', ' ', 4, 5) None None
Token('NUMBER', '42', 5, 7) 42 None
```

`token.groups` gives the spans in the same form `match()` returns them.

Where no rule matches, `lex()` raises `pyre.LexError`, a `ValueError`, after
yielding the tokens before that point. Like `PatternError`, it carries `text`,
`pos`, `lineno` and `colno`. To pass unknown characters through instead, end
the rules with a catch-all such as `('OTHER', '.')`, as `calc` does.

---

## Powerful Set Operators

Test whether two REs recognize the same language, or whether one is a subset of another:

```python
import pyre

a  = pyre.parse("a(?:b|c)")
b  = pyre.parse("ab|ac")
ab = pyre.parse("ab")

pyre.equal(a, b)                                   # True  — same language
pyre.equal("a(?:b|c)", "ab|ac")                    # True  — string helper form
pyre.compile(a ^ b).isempty()                      # True  — XOR is the empty language
pyre.subset(ab, a)                                 # True  — ab ⊆ a(?:b|c)
pyre.isempty("a & b")                              # True  — disjoint intersection
```

Set-operator composition lives on parsed `Regex` values. Compiled `DFA` values
are executable matchers, so compose expressions before compiling. Operators do
not parse strings implicitly; helper functions such as `pyre.equal()` and
`pyre.isempty()` accept strings as a convenience.

Composition keeps capture groups. Groups are numbered left to right when you
compile, so `pyre.parse("(a)") | pyre.parse("(b)")` reports the same groups as
`pyre.parse("(a)|(b)")`. Groups report only from the part of a pattern that
matched: the excluded side of `-`, the whole of `~`, and the losing side of
`^` never report. `pyre.equal()` and `pyre.subset()` ignore groups and compare
languages only.

### Operator Precedence

From loosest to tightest binding:

| Operators | Meaning | Example |
|---|---|---|
| `\|` `^` `-` | union, symmetric difference, difference | `a\|b-a` is `(a\|b)-a` |
| `&` | intersection | `a\|.&b` is `a\|(.&b)` |
| (adjacent) | concatenation | `ab&a.` is `(ab)&(a.)` |
| `~` | complement | `~ab` is `(~a)b` |
| `*` `+` `?` `{m,n}` | repetition | `~a*` is `~(a*)` |

Binary operators group left to right. `^` is symmetric difference, not a
start anchor. `-` is a literal wherever an operand begins, so `-a` matches
"-a" and `a|-b` matches "a" or "-b". When in doubt, group with `(?:...)`.

---

## Project Structure

```
 ├── .gitignore
 ├── README.md
 ├── __init__.py
 ├── capture.py
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
 ├── test
 │   ├── __init__.py
 │   ├── test_basic.py
 │   ├── test_boolean.py
 │   ├── test_capture.py
 │   ├── test_cli.py
 │   ├── test_common.py
 │   ├── test_lexer.py
 │   ├── test_parser.py
 │   ├── test_repeat.py
 │   └── test_unicode.py
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
