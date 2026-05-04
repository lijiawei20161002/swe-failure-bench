"""
Tree-walking evaluator.
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
            return math.floor(left / right)
        if node.op == "%":
            if right == 0:
                raise EvalError("modulo by zero")
            return left % right
        if node.op == "^":
            return left ** right

    raise EvalError(f"Unknown node: {node}")
