"""Tests for RESP parser. Run: pytest tests/ -x"""
import pytest
from resp_parser import RespParser, RespError, IncompleteError


# ── simple types ──────────────────────────────────────────────────────────────

class TestSimpleTypes:
    def test_simple_string(self):
        p = RespParser()
        p.feed(b"+OK\r\n")
        assert p.get_message() == "OK"

    def test_simple_string_with_spaces(self):
        p = RespParser()
        p.feed(b"+Hello World\r\n")
        assert p.get_message() == "Hello World"

    def test_error_type(self):
        p = RespParser()
        p.feed(b"-ERR unknown command\r\n")
        msg = p.get_message()
        assert isinstance(msg, RespError)
        assert "unknown command" in msg.message

    def test_integer(self):
        p = RespParser()
        p.feed(b":42\r\n")
        assert p.get_message() == 42

    def test_negative_integer(self):
        p = RespParser()
        p.feed(b":-7\r\n")
        assert p.get_message() == -7

    def test_zero_integer(self):
        p = RespParser()
        p.feed(b":0\r\n")
        assert p.get_message() == 0


# ── bulk strings ──────────────────────────────────────────────────────────────

class TestBulkStrings:
    def test_bulk_string(self):
        p = RespParser()
        p.feed(b"$6\r\nfoobar\r\n")
        assert p.get_message() == b"foobar"

    def test_null_bulk_string(self):
        p = RespParser()
        p.feed(b"$-1\r\n")
        assert p.get_message() is None

    def test_empty_bulk_string(self):
        p = RespParser()
        p.feed(b"$0\r\n\r\n")
        assert p.get_message() == b""

    def test_bulk_string_with_binary_data(self):
        p = RespParser()
        data = bytes(range(10))
        msg = b"$10\r\n" + data + b"\r\n"
        p.feed(msg)
        assert p.get_message() == data

    def test_bulk_string_containing_crlf(self):
        """Bulk string data may contain embedded \\r\\n — must use length, not line scan."""
        p = RespParser()
        p.feed(b"$7\r\nfoo\r\nba\r\n")   # 7 bytes: "foo\r\nba"
        assert p.get_message() == b"foo\r\nba"

    def test_two_consecutive_bulk_strings(self):
        """After parsing one bulk string the parser must be at correct offset for next."""
        p = RespParser()
        p.feed(b"$3\r\nfoo\r\n$3\r\nbar\r\n")
        assert p.get_message() == b"foo"
        assert p.get_message() == b"bar"


# ── arrays ────────────────────────────────────────────────────────────────────

class TestArrays:
    def test_simple_array(self):
        p = RespParser()
        p.feed(b"*2\r\n$3\r\nfoo\r\n$3\r\nbar\r\n")
        assert p.get_message() == [b"foo", b"bar"]

    def test_null_array(self):
        p = RespParser()
        p.feed(b"*-1\r\n")
        assert p.get_message() is None

    def test_empty_array(self):
        p = RespParser()
        p.feed(b"*0\r\n")
        assert p.get_message() == []

    def test_mixed_type_array(self):
        p = RespParser()
        p.feed(b"*3\r\n:1\r\n:2\r\n:3\r\n")
        assert p.get_message() == [1, 2, 3]

    def test_nested_array(self):
        p = RespParser()
        p.feed(b"*2\r\n*2\r\n:1\r\n:2\r\n*2\r\n:3\r\n:4\r\n")
        assert p.get_message() == [[1, 2], [3, 4]]

    def test_array_of_bulk_strings_distinct(self):
        """All elements of the array must be distinct, not duplicates of element[0]."""
        p = RespParser()
        p.feed(b"*3\r\n$3\r\nSET\r\n$3\r\nkey\r\n$5\r\nvalue\r\n")
        result = p.get_message()
        assert result == [b"SET", b"key", b"value"], f"got {result!r}"


# ── streaming / pipelining ────────────────────────────────────────────────────

class TestStreaming:
    def test_incomplete_raises(self):
        p = RespParser()
        p.feed(b"+OK")   # no \r\n yet
        with pytest.raises(IncompleteError):
            p.get_message()

    def test_feed_in_chunks(self):
        p = RespParser()
        p.feed(b"$6\r\n")
        p.feed(b"foo")
        assert not p.has_message()
        p.feed(b"bar\r\n")
        assert p.get_message() == b"foobar"

    def test_pipelining_two_commands(self):
        p = RespParser()
        p.feed(b"+OK\r\n+PONG\r\n")
        assert p.get_message() == "OK"
        assert p.get_message() == "PONG"

    def test_pipelining_mixed_types(self):
        p = RespParser()
        p.feed(b":1\r\n$3\r\nfoo\r\n*2\r\n:2\r\n:3\r\n")
        assert p.get_message() == 1
        assert p.get_message() == b"foo"
        assert p.get_message() == [2, 3]

    def test_has_message(self):
        p = RespParser()
        assert not p.has_message()
        p.feed(b"+OK\r\n")
        assert p.has_message()
        p.get_message()
        assert not p.has_message()


# ── error handling ────────────────────────────────────────────────────────────

class TestErrorHandling:
    def test_invalid_type_byte_raises(self):
        p = RespParser()
        with pytest.raises((ValueError, RespError)):
            p.feed(b"@invalid\r\n")
            p.get_message()

    def test_invalid_integer_raises(self):
        p = RespParser()
        with pytest.raises((ValueError, Exception)):
            p.feed(b":not_a_number\r\n")
            p.get_message()

    def test_negative_bulk_length_other_than_minus_one_raises(self):
        """Only $-1 is valid (null). Other negative lengths must raise."""
        p = RespParser()
        with pytest.raises((ValueError, Exception)):
            p.feed(b"$-2\r\n")
            p.get_message()
