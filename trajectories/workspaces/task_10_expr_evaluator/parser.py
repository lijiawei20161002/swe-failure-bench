"""
Recursive-descent parser producing an AST.

Grammar (correct):
    expr   = term   (('+' | '-') term)*
    term   = factor (('*' | '/' | '//' | '%') factor)*
    factor = unary  ('^' factor)?          ← right-associative power
    unary  = '-' unary | primary
    primary= NUM | '(' expr ')'
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from lexer import TT, Token


# ── AST nodes ─────────────────────────────────────────────────────────────────

@dataclass
class Num:
    value: float

@dataclass
class BinOp:
    op: str
    left: Any
    right: Any

@dataclass
class UnaryMinus:
    operand: Any


class ParseError(Exception):
    pass


# ── parser ────────────────────────────────────────────────────────────────────

class Parser:
    def __init__(self, tokens: list[Token]):
        self._tokens = tokens
        self._pos = 0

    def _peek(self) -> Token:
        return self._tokens[self._pos]

    def _eat(self, tt: TT) -> Token:
        tok = self._peek()
        if tok.type != tt:
            raise ParseError(f"Expected {tt}, got {tok}")
        self._pos += 1
        return tok

    def parse(self):
        node = self._expr()
        self._eat(TT.EOF)
        return node

    def _expr(self):
        node = self._term()
        while self._peek().type in (TT.PLUS, TT.MINUS):
            op = self._peek().value
            self._pos += 1
            node = BinOp(op, node, self._term())
        return node

    def _term(self):
        node = self._factor()
        while self._peek().type in (TT.STAR, TT.SLASH, TT.DSLASH, TT.PERCENT):
            op = self._peek().value
            self._pos += 1
            node = BinOp(op, node, self._factor())
        return node

    def _factor(self):
        node = self._unary()
        if self._peek().type == TT.CARET:
            op = self._peek().value
            self._pos += 1
            node = BinOp(op, node, self._factor())
        return node

    def _unary(self):
        if self._peek().type == TT.MINUS:
            self._pos += 1
            return UnaryMinus(self._unary())
        return self._primary()

    def _primary(self):
        tok = self._peek()
        if tok.type == TT.NUM:
            self._pos += 1
            v = float(tok.value)
            return Num(int(v) if v == int(v) else v)
        if tok.type == TT.LPAREN:
            self._pos += 1
            node = self._expr()
            self._eat(TT.RPAREN)
            return node
        raise ParseError(f"Unexpected token: {tok}")
