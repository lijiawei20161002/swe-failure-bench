"""
Python-like source-code tokenizer.

Produces a flat stream of Token objects from a source string.

Supported token types (matching Python's tokenize module):
  NAME, NUMBER, STRING, OP, NEWLINE, INDENT, DEDENT, COMMENT, ENDMARKER

Based on CPython's tokenize.py patterns.

Usage:
    tokens = list(tokenize("x = 1 + 2\\n"))
    # → [Token('NAME','x'), Token('OP','='), Token('NUMBER','1'), ...]
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True)
class Token:
    type: str
    value: str
    line: int = 0
    col: int = 0

    def __repr__(self):
        return f"Token({self.type!r}, {self.value!r})"


class TokenizeError(Exception):
    pass


# ── regex patterns ────────────────────────────────────────────────────────────

_PATTERNS = [
    ("COMMENT",  r"#[^\n]*"),
    ("STRING",   r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\''),
    ("NUMBER",   r"\d+(?:\.\d+)?(?:[eE][+-]?\d+)?"),
    ("NAME",     r"[A-Za-z_]\w*"),
    ("OP",       r"[+\-*/%//=<>!&|^~@,.;:()\[\]{}]"),
    ("NEWLINE",  r"\n"),
    ("SKIP",     r"[ \t]+"),   # horizontal whitespace
    ("MISMATCH", r"."),
]

_MASTER = re.compile(
    "|".join(f"(?P<{name}>{pat})" for name, pat in _PATTERNS)
)

_KEYWORDS = frozenset([
    "False", "None", "True", "and", "as", "assert", "async", "await",
    "break", "class", "continue", "def", "del", "elif", "else", "except",
    "finally", "for", "from", "global", "if", "import", "in", "is",
    "lambda", "nonlocal", "not", "or", "pass", "raise", "return", "try",
    "while", "with", "yield",
])

_ESCAPE_MAP = {
    "n": "\n", "t": "\t", "r": "\r", "\\": "\\",
    "'": "'", '"': '"', "a": "\a", "b": "\b",
    "f": "\f", "v": "\v", "0": "\0",
}


def tokenize(source: str) -> Iterator[Token]:
    """Yield Token objects for every meaningful token in *source*."""
    indent_stack = [0]
    line_num = 1
    line_start = 0
    at_line_start = True

    pos = 0
    while pos < len(source):
        # ── indentation ───────────────────────────────────────────────────────
        if at_line_start and source[pos] not in ("\n", "#"):
            # Measure indent
            indent_end = pos
            while indent_end < len(source) and source[indent_end] in " \t":
                indent_end += 1
            indent = indent_end - pos
            if indent > indent_stack[-1]:
                indent_stack.append(indent)
                yield Token("INDENT", source[pos:indent_end], line_num, 0)
            elif indent < indent_stack[-1]:
                while indent_stack[-1] > indent:
                    indent_stack.pop()
                    yield Token("DEDENT", "", line_num, 0)
                if indent_stack[-1] != indent:
                    raise TokenizeError(f"Indentation error at line {line_num}")
            at_line_start = False

        mo = _MASTER.match(source, pos)
        if not mo:
            raise TokenizeError(f"Unexpected character {source[pos]!r} at line {line_num}")

        kind = mo.lastgroup
        value = mo.group()
        col = pos - line_start
        pos = mo.end()

        if kind == "SKIP":
            continue
        elif kind == "MISMATCH":
            raise TokenizeError(f"Unexpected character {value!r} at line {line_num}")
        elif kind == "NEWLINE":
            yield Token("NEWLINE", value, line_num, col)
            line_num += 1
            line_start = pos
            at_line_start = True
            continue
        elif kind == "NAME" and value in _KEYWORDS:
            kind = "KEYWORD"
        elif kind == "STRING":
            pass

        yield Token(kind, value, line_num, col)

    # Emit any pending DEDENTs
    while len(indent_stack) > 1:
        indent_stack.pop()
        yield Token("DEDENT", "", line_num, 0)

    yield Token("ENDMARKER", "", line_num, 0)
