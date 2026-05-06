"""
Length-prefixed frame encoder for a binary message protocol.

Each frame is:
    [ 4-byte unsigned length ] [ payload bytes ]

The length field records the number of payload bytes that follow.
Frames are designed to be written to a socket or byte stream and
decoded by the paired Decoder in decoder.py.
"""

from __future__ import annotations

import struct


class Encoder:
    """Encodes messages into length-prefixed binary frames."""

    _FMT = ">I"   # big-endian unsigned int (network byte order)

    def encode(self, payload: bytes) -> bytes:
        """Return a length-prefixed frame for *payload*."""
        header = struct.pack(self._FMT, len(payload))
        return header + payload

    def encode_many(self, payloads: list[bytes]) -> bytes:
        """Encode multiple payloads into a single byte string."""
        return b"".join(self.encode(p) for p in payloads)
