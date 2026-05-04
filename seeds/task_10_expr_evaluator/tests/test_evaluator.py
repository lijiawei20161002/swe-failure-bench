"""Tests for expression evaluator. Run: pytest tests/ -x"""
import math
import pytest
from lexer import tokenize
from parser import Parser, ParseError
from evaluator import evaluate


def calc(expr: str) -> float:
    tokens = tokenize(expr)
    ast = Parser(tokens).parse()
    return evaluate(ast)


# ── arithmetic ────────────────────────────────────────────────────────────────

class TestArithmetic:
    def test_addition(self):
        assert calc("1 + 2") == 3

    def test_subtraction(self):
        assert calc("10 - 3") == 7

    def test_multiplication(self):
        assert calc("4 * 5") == 20

    def test_division(self):
        assert abs(calc("7 / 2") - 3.5) < 1e-9

    def test_precedence_mul_over_add(self):
        assert calc("2 + 3 * 4") == 14

    def test_parentheses(self):
        assert calc("(2 + 3) * 4") == 20

    def test_division_by_zero(self):
        from evaluator import EvalError
        with pytest.raises(EvalError):
            calc("1 / 0")


# ── unary minus ───────────────────────────────────────────────────────────────

class TestUnaryMinus:
    def test_unary_minus_literal(self):
        """Bare negative number: -5 → -5"""
        assert calc("-5") == -5

    def test_unary_minus_in_expr(self):
        assert calc("-3 + 10") == 7

    def test_unary_minus_nested(self):
        assert calc("--4") == 4

    def test_unary_minus_with_mul(self):
        assert calc("-2 * 3") == -6

    def test_unary_minus_parenthesized(self):
        assert calc("-(3 + 4)") == -7


# ── floor division ────────────────────────────────────────────────────────────

class TestFloorDiv:
    def test_positive_floor_div(self):
        assert calc("7 // 2") == 3

    def test_negative_floor_div_floors_toward_neg_inf(self):
        """
        Python semantics: -7 // 2 = -4 (floor toward -∞).
        Truncation toward zero would give -3 — that's the bug.
        """
        assert calc("-7 // 2") == -4, "-7 // 2 must be -4 (floor), not -3 (truncation)"

    def test_negative_divisor_floor_div(self):
        assert calc("7 // -2") == -4, "7 // -2 must be -4 (floor), not -3"

    def test_both_negative_floor_div(self):
        assert calc("-7 // -2") == 3

    def test_modulo_consistency(self):
        """Invariant: (a // b) * b + (a % b) == a for all integer inputs."""
        for a in [-7, -6, 6, 7]:
            for b in [-3, -2, 2, 3]:
                expected = a
                got = calc(f"({a} // {b}) * {b} + ({a} % {b})")
                assert abs(got - expected) < 1e-9, (
                    f"({a} // {b}) * {b} + ({a} % {b}) = {got}, expected {expected}"
                )


# ── power operator ────────────────────────────────────────────────────────────

class TestPower:
    def test_simple_power(self):
        assert calc("2 ^ 3") == 8

    def test_power_is_right_associative(self):
        """
        2^3^2 must parse as 2^(3^2) = 2^9 = 512, NOT (2^3)^2 = 64.
        Right-associativity is the standard mathematical convention and
        matches Python's ** operator.
        """
        assert calc("2 ^ 3 ^ 2") == 512, (
            "2^3^2 should be 2^(3^2)=512. Got wrong result — power is left-associative."
        )

    def test_power_left_chain(self):
        """4^3^2 = 4^9 = 262144."""
        assert calc("4 ^ 3 ^ 2") == 4 ** (3 ** 2)

    def test_power_higher_precedence_than_mul(self):
        assert calc("2 * 3 ^ 2") == 18

    def test_power_with_unary_minus_base(self):
        """(-2)^3 = -8"""
        assert calc("(-2) ^ 3") == -8


# ── combined ──────────────────────────────────────────────────────────────────

class TestCombined:
    def test_complex_expr(self):
        # -3 + 2^3^1 = -3 + 2^3 = -3 + 8 = 5
        assert calc("-3 + 2 ^ 3 ^ 1") == 5

    def test_matches_python_eval(self):
        """The evaluator must agree with Python for these expressions."""
        cases = [
            ("-7 // 2", -7 // 2),
            ("2 ** 3 ** 2".replace("**", "^"), 2 ** (3 ** 2)),
            ("-3 * -4", 12),
            ("(1 + 2) * (3 - 4)", -3),
        ]
        for expr, expected in cases:
            assert calc(expr) == expected, f"calc({expr!r}) != {expected}"
