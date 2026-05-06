"""
Tests for the length-prefixed frame codec.
Run: pip install pytest && pytest tests/ -x -q
"""
import struct
import pytest
from encoder import Encoder
from decoder import Decoder


class TestRoundTrip:
    """End-to-end encode → decode round trips."""

    def test_empty_payload(self):
        enc, dec = Encoder(), Decoder()
        wire = enc.encode(b"")
        frames = dec.decode_all(wire)
        assert frames == [b""]

    def test_short_payload(self):
        """Any non-zero length payload fails when byte order is mismatched."""
        enc, dec = Encoder(), Decoder()
        msg = b"hello"
        wire = enc.encode(msg)
        frames = dec.decode_all(wire)
        assert frames == [msg]

    def test_exactly_256_bytes(self):
        """
        256-byte payload is the first length where little-endian and
        big-endian encodings differ in the 4-byte header:
          little-endian 256 → b'\\x00\\x01\\x00\\x00'
          big-endian    256 → b'\\x00\\x00\\x01\\x00'
        A mismatch causes the decoder to read a wrong length, producing
        either no frame (waiting for more data) or a garbled payload.
        """
        enc, dec = Encoder(), Decoder()
        msg = b"A" * 256
        wire = enc.encode(msg)
        frames = dec.decode_all(wire)
        assert frames == [msg], (
            f"Round-trip failed for a 256-byte payload. "
            f"Got {len(frames)} frame(s); expected 1. "
            "Check that Encoder and Decoder use the same byte order for "
            "the 4-byte length prefix (both '<I' or both '>I')."
        )

    def test_large_payload(self):
        """64 KB payload — byte-order mismatch is unambiguous here."""
        enc, dec = Encoder(), Decoder()
        msg = bytes(range(256)) * 256   # 65536 bytes
        wire = enc.encode(msg)
        frames = dec.decode_all(wire)
        assert frames == [msg]

    def test_multiple_frames(self):
        enc, dec = Encoder(), Decoder()
        messages = [b"frame one", b"x" * 300, b"frame three"]
        wire = enc.encode_many(messages)
        frames = dec.decode_all(wire)
        assert frames == messages

    def test_fragmented_delivery(self):
        """Decoder must handle data arriving in small chunks."""
        enc, dec = Encoder(), Decoder()
        msg = b"Y" * 512
        wire = enc.encode(msg)
        # Feed one byte at a time
        for byte in wire:
            dec.feed(bytes([byte]))
        frames = dec.frames()
        assert frames == [msg]

    def test_multiple_frames_fragmented(self):
        enc, dec = Encoder(), Decoder()
        messages = [b"a" * 300, b"b" * 400, b"c" * 100]
        wire = enc.encode_many(messages)
        # Feed in 7-byte chunks
        for i in range(0, len(wire), 7):
            dec.feed(wire[i : i + 7])
        assert dec.frames() == messages

    def test_payload_content_preserved(self):
        """All 256 byte values must survive a round-trip."""
        enc, dec = Encoder(), Decoder()
        msg = bytes(range(256)) * 2   # 512 bytes, all byte values
        wire = enc.encode(msg)
        frames = dec.decode_all(wire)
        assert frames == [msg]


class TestEncoderFormat:
    def test_header_length(self):
        enc = Encoder()
        frame = enc.encode(b"test")
        assert len(frame) == 4 + 4   # 4-byte header + 4-byte payload

    def test_header_encodes_payload_length(self):
        enc = Encoder()
        payload = b"hello world"
        frame = enc.encode(payload)
        # Regardless of byte order, the decoded length must equal len(payload)
        length_le = struct.unpack("<I", frame[:4])[0]
        length_be = struct.unpack(">I", frame[:4])[0]
        assert length_le == len(payload) or length_be == len(payload)

    def test_encode_many_concatenates(self):
        enc = Encoder()
        parts = [b"one", b"two", b"three"]
        combined = enc.encode_many(parts)
        individual = b"".join(enc.encode(p) for p in parts)
        assert combined == individual


class TestDecoderStateful:
    def test_partial_header_buffered(self):
        dec = Decoder()
        dec.feed(b"\x00\x00")   # incomplete 4-byte header
        assert dec.frames() == []

    def test_partial_payload_buffered(self):
        enc, dec = Encoder(), Decoder()
        msg = b"hello"
        wire = enc.encode(msg)
        dec.feed(wire[:5])   # partial
        assert dec.frames() == []
        dec.feed(wire[5:])
        assert dec.frames() == [msg]

    def test_decoder_resets_between_calls(self):
        enc, dec = Encoder(), Decoder()
        msg1 = b"first"
        msg2 = b"B" * 300
        dec.feed(enc.encode(msg1))
        f1 = dec.frames()
        dec.feed(enc.encode(msg2))
        f2 = dec.frames()
        assert f1 == [msg1]
        assert f2 == [msg2]
