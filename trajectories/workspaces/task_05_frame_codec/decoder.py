"""
Length-prefixed frame decoder for a binary message protocol.

Reads frames produced by the Encoder in encoder.py.
Each frame:
    [ 4-byte unsigned length ] [ payload bytes ]
"""

from __future__ import annotations

import struct


class Decoder:
    """
    Stateful decoder that reassembles frames from a stream of bytes.

    Feed raw bytes incrementally via feed(); call frames() to retrieve
    any complete frames that have been assembled.
    """

    _HEADER = 4   # bytes in the length prefix
    _FMT = ">I"   # big-endian unsigned int (network byte order)
                  # NOTE: must match the byte order used by Encoder._FMT.
                  # Current Encoder uses '<I' (little-endian) — MISMATCH.

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> None:
        """Append raw bytes to the internal buffer."""
        self._buf.extend(data)

    def frames(self) -> list[bytes]:
        """
        Extract and return all complete frames currently in the buffer.
        Partial frames remain buffered until more data arrives.
        """
        result = []
        while len(self._buf) >= self._HEADER:
            (length,) = struct.unpack_from(self._FMT, self._buf, 0)
            if len(self._buf) < self._HEADER + length:
                break
            payload = bytes(self._buf[self._HEADER : self._HEADER + length])
            result.append(payload)
            del self._buf[: self._HEADER + length]
        return result

    def decode_all(self, data: bytes) -> list[bytes]:
        """Convenience: feed data and return all complete frames at once."""
        self.feed(data)
        return self.frames()
