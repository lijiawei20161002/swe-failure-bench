"""Tests for Rope. Run: pytest tests/ -x"""
import pytest
from rope import Rope


# ── construction / str ────────────────────────────────────────────────────────

class TestConstruction:
    def test_empty(self):
        assert str(Rope()) == ""
        assert len(Rope()) == 0

    def test_short(self):
        r = Rope("hello")
        assert str(r) == "hello"
        assert len(r) == 5

    def test_long_splits_into_tree(self):
        s = "abcdefghijklmnopqrstuvwxyz"
        r = Rope(s)
        assert str(r) == s
        assert len(r) == 26

    def test_unicode(self):
        s = "héllo wörld"
        assert str(Rope(s)) == s


# ── index ─────────────────────────────────────────────────────────────────────

class TestIndex:
    def test_index_first(self):
        assert Rope("hello").index(0) == "h"

    def test_index_last(self):
        assert Rope("hello").index(4) == "o"

    def test_index_all(self):
        s = "abcdefghijklmnopqrstuvwxyz"
        r = Rope(s)
        for i, ch in enumerate(s):
            assert r.index(i) == ch

    def test_index_out_of_range(self):
        r = Rope("abc")
        with pytest.raises(IndexError):
            r.index(3)
        with pytest.raises(IndexError):
            r.index(-1)


# ── concat ────────────────────────────────────────────────────────────────────

class TestConcat:
    def test_concat_two_strings(self):
        r = Rope("Hello, ").concat(Rope("World!"))
        assert str(r) == "Hello, World!"

    def test_concat_preserves_content(self):
        a = "The quick brown fox "
        b = "jumps over the lazy dog."
        r = Rope(a) + Rope(b)
        assert str(r) == a + b

    def test_concat_empty_left(self):
        r = Rope("") + Rope("abc")
        assert str(r) == "abc"

    def test_concat_empty_right(self):
        r = Rope("abc") + Rope("")
        assert str(r) == "abc"

    def test_len_after_concat(self):
        r = Rope("hello") + Rope(" world")
        assert len(r) == 11


# ── split ─────────────────────────────────────────────────────────────────────

class TestSplit:
    def test_split_at_zero(self):
        left, right = Rope("hello").split(0)
        assert str(left) == ""
        assert str(right) == "hello"

    def test_split_at_end(self):
        left, right = Rope("hello").split(5)
        assert str(left) == "hello"
        assert str(right) == ""

    def test_split_middle(self):
        left, right = Rope("hello").split(2)
        assert str(left) == "he", f"left={str(left)!r}"
        assert str(right) == "llo", f"right={str(right)!r}"

    def test_split_long_string(self):
        """Split a string longer than _MAX_LEAF (forces internal nodes)."""
        s = "abcdefghijklmnopqrstuvwxyz"
        for i in range(len(s) + 1):
            r = Rope(s)
            left, right = r.split(i)
            assert str(left) == s[:i], f"split({i}): left={str(left)!r} != {s[:i]!r}"
            assert str(right) == s[i:], f"split({i}): right={str(right)!r} != {s[i:]!r}"

    def test_split_preserves_all_characters(self):
        """No character should be lost during split."""
        s = "Hello, World! How are you today?"
        r = Rope(s)
        for i in range(len(s) + 1):
            left, right = r.split(i)
            reconstructed = str(left) + str(right)
            assert reconstructed == s, (
                f"split({i}) lost data: {reconstructed!r} != {s!r}"
            )

    def test_split_out_of_range(self):
        r = Rope("abc")
        with pytest.raises(IndexError):
            r.split(4)
        with pytest.raises(IndexError):
            r.split(-1)


# ── slice ─────────────────────────────────────────────────────────────────────

class TestSlice:
    def test_slice_basic(self):
        r = Rope("hello world")
        assert str(r[0:5]) == "hello"

    def test_slice_all(self):
        s = "hello world"
        r = Rope(s)
        assert str(r[0:len(s)]) == s

    def test_slice_empty(self):
        r = Rope("hello")
        assert str(r[2:2]) == ""

    def test_slice_consistency_with_split(self):
        s = "abcdefghijklmnop"
        r = Rope(s)
        for start in range(len(s)):
            for stop in range(start, len(s) + 1):
                result = str(r[start:stop])
                expected = s[start:stop]
                assert result == expected, (
                    f"r[{start}:{stop}] = {result!r}, expected {expected!r}"
                )


# ── round-trip property ───────────────────────────────────────────────────────

class TestRoundTrip:
    def test_concat_then_split_roundtrip(self):
        """concat(a, b).split(len(a)) == (a, b)"""
        pairs = [
            ("", ""),
            ("hello", ""),
            ("", "world"),
            ("hello", "world"),
            ("abcdefgh", "ijklmnopqrstuvwxyz"),
        ]
        for a, b in pairs:
            r = Rope(a) + Rope(b)
            left, right = r.split(len(a))
            assert str(left) == a, f"left mismatch for ({a!r}, {b!r})"
            assert str(right) == b, f"right mismatch for ({a!r}, {b!r})"
