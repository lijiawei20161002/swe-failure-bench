"""
RESP (REdis Serialization Protocol v2) parser.

Parses the wire format used by Redis for both commands and replies.

RESP types:
  Simple Strings:  +OK\r\n
  Errors:          -ERR message\r\n
  Integers:        :42\r\n
  Bulk Strings:    $6\r\nfoobar\r\n   ($-1\r\n = null)
  Arrays:          *3\r\n...           (*-1\r\n = null array)

Reference: https://redis.io/docs/reference/protocol-spec/

Public API:
    parser = RespParser()
    parser.feed(b"+OK\r\n")
    msg = parser.get_message()   # → "OK"  (str for Simple String)

    parser.feed(b"*2\r\n$3\r\nfoo\r\n$3\r\nbar\r\n")
    msg = parser.get_message()   # → ["foo", "bar"]

Types returned:
  Simple String → str
  Error         → RespError(message: str)
  Integer       → int
  Bulk String   → bytes (or None for null)
  Array         → list (or None for null)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class RespError(Exception):
    """Represents a Redis error reply."""
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class IncompleteError(Exception):
    """Raised when the buffer doesn't yet contain a complete message."""


@dataclass
class RespParser:
    _buf: bytearray = field(default_factory=bytearray)

    def __post_init__(self):
        self._messages: list[Any] = []

    def feed(self, data: bytes) -> None:
        """Append bytes to the internal buffer and parse any complete messages."""
        self._buf.extend(data)
        self._parse()

    def get_message(self) -> Any:
        """
        Return the next parsed message, or raise IncompleteError if none ready.
        """
        if not self._messages:
            raise IncompleteError("no complete message in buffer")
        return self._messages.pop(0)

    def has_message(self) -> bool:
        return bool(self._messages)

    # ── internal parsing ──────────────────────────────────────────────────────

    def _parse(self) -> None:
        while True:
            try:
                value, consumed = _parse_one(self._buf, 0)
                self._messages.append(value)
                del self._buf[:consumed]
            except IncompleteError:
                break


def _parse_one(buf: bytearray, pos: int) -> tuple[Any, int]:
    """
    Parse one RESP value starting at *pos* in *buf*.
    Returns (value, new_pos_after_consumed_bytes).
    Raises IncompleteError if buf is too short.
    """
    if pos >= len(buf):
        raise IncompleteError

    type_byte = chr(buf[pos])
    pos += 1

    if type_byte == "+":
        # Simple String
        line, pos = _read_line(buf, pos)
        return line.decode("utf-8"), pos

    elif type_byte == "-":
        # Error
        line, pos = _read_line(buf, pos)
        return RespError(line.decode("utf-8")), pos

    elif type_byte == ":":
        # Integer
        line, pos = _read_line(buf, pos)
        return int(line), pos

    elif type_byte == "$":
        # Bulk String
        line, pos = _read_line(buf, pos)
        length = int(line)
        if length == -1:
            return None, pos
        if length < -1:
            raise ValueError(f"invalid bulk string length: {length}")
        if pos + length + 2 > len(buf):
            raise IncompleteError
        data = bytes(buf[pos : pos + length])
        pos += length
        # Consume trailing \r\n
        if bytes(buf[pos : pos + 2]) != b"\r\n":
            raise ValueError("expected \\r\\n after bulk string data")
        pos += 2
        return data, pos

    elif type_byte == "*":
        # Array
        line, pos = _read_line(buf, pos)
        count = int(line)
        if count == -1:
            return None, pos
        items = []
        for _ in range(count):
            item, pos = _parse_one(buf, pos)
            items.append(item)
        return items, pos

    else:
        raise ValueError(f"invalid RESP type byte: {type_byte!r}")


def _read_line(buf: bytearray, pos: int) -> tuple[bytes, int]:
    """
    Read until \\r\\n. Returns (line_bytes_without_crlf, new_pos).
    Raises IncompleteError if \\r\\n not found.
    """
    end = buf.find(b"\r\n", pos)
    if end == -1:
        raise IncompleteError
    line = bytes(buf[pos:end])
    return line, end + 2
