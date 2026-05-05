"""Tests for tokenizer. Run: pytest tests/ -x"""
import pytest
from tokenizer import tokenize, Token, TokenizeError


def tok(source):
    """Return list of tokens, excluding ENDMARKER."""
    return [t for t in tokenize(source) if t.type != "ENDMARKER"]


def types(source):
    return [t.type for t in tok(source)]


def vals(source):
    return [t.value for t in tok(source)]


# ── basic tokens ──────────────────────────────────────────────────────────────

class TestBasic:
    def test_simple_expression(self):
        result = tok("x = 1\n")
        assert [t.type for t in result] == ["NAME", "OP", "NUMBER", "NEWLINE"]

    def test_name_vs_keyword(self):
        result = tok("if x\n")
        assert result[0].type == "KEYWORD"
        assert result[0].value == "if"
        assert result[1].type == "NAME"
        assert result[1].value == "x"

    def test_comment_token(self):
        result = tok("# hello\n")
        assert result[0].type == "COMMENT"
        assert result[0].value == "# hello"

    def test_number_float(self):
        result = tok("3.14\n")
        assert result[0].type == "NUMBER"
        assert result[0].value == "3.14"

    def test_number_scientific(self):
        result = tok("1e10\n")
        assert result[0].type == "NUMBER"

    def test_unknown_char_raises(self):
        with pytest.raises(TokenizeError):
            tok("$bad\n")


# ── string literals ───────────────────────────────────────────────────────────

class TestStrings:
    def test_double_quoted_string_value(self):
        """Token value must be the interpreted content, not the source form."""
        result = tok('"hello"\n')
        s = next(t for t in result if t.type == "STRING")
        assert s.value == "hello"   # no quotes, no escapes

    def test_single_quoted_string_value(self):
        result = tok("'world'\n")
        s = next(t for t in result if t.type == "STRING")
        assert s.value == "world"

    def test_escape_newline(self):
        result = tok(r'"line1\nline2"' + "\n")
        s = next(t for t in result if t.type == "STRING")
        assert s.value == "line1\nline2"

    def test_escape_tab(self):
        result = tok(r'"a\tb"' + "\n")
        s = next(t for t in result if t.type == "STRING")
        assert s.value == "a\tb"

    def test_escaped_backslash(self):
        result = tok(r'"a\\b"' + "\n")
        s = next(t for t in result if t.type == "STRING")
        assert s.value == "a\\b"

    def test_raw_string_no_escape_processing(self):
        """Raw strings (r"...") must NOT interpret escape sequences."""
        result = tok(r'r"line1\nline2"' + "\n")
        s = next(t for t in result if t.type == "STRING")
        # The value should be the literal backslash-n, not a newline character
        assert s.value == r"line1\nline2"

    def test_raw_string_single_quote(self):
        result = tok(r"r'\t'" + "\n")
        s = next(t for t in result if t.type == "STRING")
        assert s.value == r"\t"

    def test_triple_double_quoted(self):
        """Triple-quoted strings can span multiple lines."""
        source = '"""hello\nworld"""\n'
        result = tok(source)
        s = next(t for t in result if t.type == "STRING")
        assert s.value == "hello\nworld"

    def test_triple_single_quoted(self):
        source = "'''line1\nline2'''\n"
        result = tok(source)
        s = next(t for t in result if t.type == "STRING")
        assert s.value == "line1\nline2"

    def test_triple_raw_string(self):
        source = 'r"""no\\escape"""\n'
        result = tok(source)
        s = next(t for t in result if t.type == "STRING")
        assert s.value == r"no\escape"


# ── indentation ───────────────────────────────────────────────────────────────

class TestIndentation:
    def test_indent_and_dedent(self):
        source = "if True:\n    x = 1\ny = 2\n"
        toks = tok(source)
        type_list = [t.type for t in toks]
        assert "INDENT" in type_list
        assert "DEDENT" in type_list

    def test_multiple_dedents(self):
        source = "if True:\n    if True:\n        x = 1\ny = 2\n"
        toks = tok(source)
        dedents = [t for t in toks if t.type == "DEDENT"]
        assert len(dedents) == 2

    def test_bad_indent_raises(self):
        source = "if True:\n    x = 1\n  y = 2\n"  # dedent to invalid level
        with pytest.raises(TokenizeError):
            tok(source)


# ── line / column numbers ─────────────────────────────────────────────────────

class TestLineCol:
    def test_line_numbers(self):
        source = "x = 1\ny = 2\n"
        toks = [t for t in tokenize(source) if t.type not in ("ENDMARKER", "NEWLINE")]
        xs = [t for t in toks if t.value == "x"]
        ys = [t for t in toks if t.value == "y"]
        assert xs[0].line == 1
        assert ys[0].line == 2

    def test_column_numbers(self):
        source = "x = 1\n"
        toks = [t for t in tokenize(source) if t.type not in ("ENDMARKER",)]
        # "x" starts at col 0, "=" at col 2, "1" at col 4
        assert toks[0].col == 0   # x
        assert toks[1].col == 2   # =
        assert toks[2].col == 4   # 1
