"""Tests for NFA regex engine. Run: pytest tests/ -x"""
import pytest
import re as stdlib_re
from regex_engine import RegexEngine, Match

engine = RegexEngine()


def match(pattern, text):
    m = engine.match(pattern, text)
    return m.group() if m else None


def findall(pattern, text):
    return engine.findall(pattern, text)


# ── literal matching ──────────────────────────────────────────────────────────

class TestLiterals:
    def test_simple_literal(self):
        assert match("abc", "abc") == "abc"

    def test_literal_in_longer_string(self):
        assert match("bc", "abcdef") == "bc"

    def test_no_match(self):
        assert match("xyz", "abc") is None

    def test_single_char(self):
        assert match("a", "ba") == "a"


# ── dot ───────────────────────────────────────────────────────────────────────

class TestDot:
    def test_dot_matches_any(self):
        assert match("a.c", "abc") == "abc"
        assert match("a.c", "aXc") == "aXc"

    def test_dot_in_findall(self):
        assert findall("a.", "aXaY") == ["aX", "aY"]


# ── quantifiers ───────────────────────────────────────────────────────────────

class TestQuantifiers:
    def test_star_zero(self):
        assert match("ab*c", "ac") == "ac"

    def test_star_multiple(self):
        assert match("ab*c", "abbbc") == "abbbc"

    def test_plus_one(self):
        assert match("ab+c", "abc") == "abc"

    def test_plus_zero_no_match(self):
        assert match("ab+c", "ac") is None

    def test_question_zero(self):
        assert match("ab?c", "ac") == "ac"

    def test_question_one(self):
        assert match("ab?c", "abc") == "abc"


# ── alternation (tests BUG A) ─────────────────────────────────────────────────

class TestAlternation:
    def test_simple_alternation_first_branch(self):
        assert match("a|b", "a") == "a"

    def test_simple_alternation_second_branch(self):
        """
        'a|b' should match 'b'. This tests the ε-closure of the split state.
        BUG A: if _e_closure only follows out1 (not out2), the second branch
        of alternation is never reachable, so 'b' won't match.
        """
        result = match("a|b", "b")
        assert result == "b", (
            f"Pattern 'a|b' should match 'b' but got {result!r}. "
            "BUG A: ε-closure doesn't follow out2 of split state."
        )

    def test_alternation_with_longer_branches(self):
        assert match("cat|dog", "dog") == "dog"

    def test_alternation_with_longer_branches_first(self):
        assert match("cat|dog", "cat") == "cat"

    def test_alternation_in_group(self):
        assert match("(a|b)c", "bc") == "bc"

    def test_alternation_findall(self):
        result = findall("cat|dog", "I have a cat and a dog")
        assert result == ["cat", "dog"], f"Got {result}"

    def test_alternation_three_options(self):
        for word in ["red", "green", "blue"]:
            assert match("red|green|blue", word) == word, f"Failed for {word!r}"

    def test_alternation_with_star(self):
        """(a|b)* should match any string of a's and b's."""
        for s in ["", "a", "b", "ababba", "aaa"]:
            # check it can match the whole string
            m = engine.fullmatch("(a|b)*", s)
            assert m is not None, f"(a|b)* should fullmatch {s!r}"


# ── character classes (tests BUG B) ──────────────────────────────────────────

class TestCharClass:
    def test_simple_class(self):
        assert match("[abc]", "b") == "b"

    def test_class_no_match(self):
        assert match("[abc]", "d") is None

    def test_range_class(self):
        """
        [a-z] must match any lowercase letter, not just 'a', '-', 'z'.
        BUG B: without range parsing, [a-z] is treated as literal chars {'a','-','z'}.
        """
        for c in "bcdefghijklmnopqrstuvwxy":
            result = match("[a-z]", c)
            assert result == c, (
                f"[a-z] should match {c!r} but got {result!r}. "
                "BUG B: character class range [a-z] not parsed — "
                "only literal 'a', '-', 'z' are in the set."
            )

    def test_digit_range_class(self):
        for c in "0123456789":
            assert match("[0-9]", c) == c, f"[0-9] should match {c!r}"

    def test_negated_class(self):
        assert match("[^abc]", "d") == "d"
        assert match("[^abc]", "a") is None

    def test_negated_range_class(self):
        assert match("[^0-9]", "a") == "a"
        assert match("[^0-9]", "5") is None

    def test_class_plus(self):
        assert findall("[a-z]+", "hello world") == ["hello", "world"]


# ── escape sequences ──────────────────────────────────────────────────────────

class TestEscapes:
    def test_digit(self):
        assert findall("\\d+", "a1b2c3") == ["1", "2", "3"]

    def test_word_char(self):
        assert match("\\w+", "hello") == "hello"

    def test_whitespace(self):
        assert match("\\s+", "   ") == "   "


# ── combined patterns ─────────────────────────────────────────────────────────

class TestCombined:
    def test_email_like(self):
        m = engine.match("\\w+@\\w+\\.\\w+", "user@example.com")
        assert m is not None
        assert m.group() == "user@example.com"

    def test_phone_like(self):
        results = findall("[0-9]{3}-[0-9]{4}", "call 555-1234 or 800-5555")
        # Note: we don't support {n} quantifier, use \d+
        results = findall("\\d+-\\d+", "call 555-1234 or 800-5555")
        assert len(results) == 2

    def test_matches_agree_with_stdlib(self):
        """Our engine must agree with Python re for basic patterns."""
        cases = [
            ("a*b", "aaab"),
            ("a|b", "b"),
            ("(a|b)+", "abba"),
            ("[0-9]+", "foo123bar"),
            ("\\d+\\.\\d+", "3.14"),
        ]
        for pattern, text in cases:
            ours = match(pattern, text)
            stdlib = stdlib_re.search(pattern, text)
            expected = stdlib.group() if stdlib else None
            assert ours == expected, (
                f"Pattern={pattern!r} text={text!r}: "
                f"our={ours!r} stdlib={expected!r}"
            )
