"""
Tree-walking evaluator.

BUG C: floor division `//` uses `int(left / right)` which truncates toward
zero, not toward negative infinity. Python's `//` always floors toward -∞.
  Example: -7 // 2  → Python gives -4 (floor), this gives -3 (truncation).
"""

from __future__ import annotations

import math
from parser import Num, BinOp, UnaryMinus


class EvalError(Exception):
    pass


def evaluate(node) -> float:
    if isinstance(node, Num):
        return node.value

    if isinstance(node, UnaryMinus):
        return -evaluate(node.operand)

    if isinstance(node, BinOp):
        left = evaluate(node.left)
        right = evaluate(node.right)

        if node.op == "+":
            return left + right
        if node.op == "-":
            return left - right
        if node.op == "*":
            return left * right
        if node.op == "/":
            if right == 0:
                raise EvalError("division by zero")
            return left / right
        if node.op == "//":
            if right == 0:
                raise EvalError("floor-division by zero")
            # BUG C: truncates toward zero instead of flooring toward -inf
            return int(left / right)   # should be: math.floor(left / right)
        if node.op == "%":
            if right == 0:
                raise EvalError("modulo by zero")
            return left % right
        if node.op == "^":
            return left ** right

    raise EvalError(f"Unknown node: {node}")
