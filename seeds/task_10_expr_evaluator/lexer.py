"""Tokenizer for arithmetic expressions."""
from __future__ import annotations
import re
from dataclasses import dataclass
from enum import Enum, auto


class TT(Enum):
    NUM = auto()
    PLUS = auto(); MINUS = auto()
    STAR = auto(); SLASH = auto(); DSLASH = auto(); PERCENT = auto()
    CARET = auto()   # ^ for power (not XOR)
    LPAREN = auto(); RPAREN = auto()
    EOF = auto()


@dataclass(frozen=True)
class Token:
    type: TT
    value: str


_PATTERNS = [
    (TT.NUM,    r"\d+(?:\.\d+)?"),
    (TT.DSLASH, r"//"),
    (TT.CARET,  r"\^"),
    (TT.PLUS,   r"\+"),
    (TT.MINUS,  r"-"),
    (TT.STAR,   r"\*"),
    (TT.SLASH,  r"/"),
    (TT.PERCENT,r"%"),
    (TT.LPAREN, r"\("),
    (TT.RPAREN, r"\)"),
]
_RE = re.compile("|".join(f"(?P<_{tt.name}>{pat})" for tt, pat in _PATTERNS))


def tokenize(expr: str) -> list[Token]:
    tokens = []
    for mo in _RE.finditer(expr.replace(" ", "")):
        name = mo.lastgroup[1:]   # strip leading _
        tt = TT[name]
        tokens.append(Token(tt, mo.group()))
    tokens.append(Token(TT.EOF, ""))
    return tokens
