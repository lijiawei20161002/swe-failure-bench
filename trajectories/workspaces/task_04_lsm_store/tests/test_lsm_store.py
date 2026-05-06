"""
Tests for LSMStore.
Run: pip install pytest && pytest tests/ -x -q
"""
import pytest
from lsm_store import LSMStore, TOMBSTONE


class TestBasicOperations:
    def test_put_and_get(self):
        s = LSMStore()
        s.put("k", "v")
        assert s.get("k") == "v"

    def test_missing_key(self):
        assert LSMStore().get("nope") is None

    def test_overwrite(self):
        s = LSMStore()
        s.put("k", "a")
        s.put("k", "b")
        assert s.get("k") == "b"

    def test_delete_in_memtable(self):
        s = LSMStore()
        s.put("k", "v")
        s.delete("k")
        assert s.get("k") is None

    def test_flush_preserves_data(self):
        s = LSMStore()
        s.put("a", "1")
        s.put("b", "2")
        s.flush()
        assert s.get("a") == "1"
        assert s.get("b") == "2"

    def test_flush_clears_memtable(self):
        s = LSMStore()
        s.put("k", "v")
        s.flush()
        # overwrite in memtable after flush
        s.put("k", "v2")
        assert s.get("k") == "v2"

    def test_delete_after_flush(self):
        s = LSMStore()
        s.put("k", "v")
        s.flush()
        s.delete("k")
        assert s.get("k") is None

    def test_multiple_flushes(self):
        s = LSMStore()
        s.put("a", "1")
        s.flush()
        s.put("b", "2")
        s.flush()
        assert s.get("a") == "1"
        assert s.get("b") == "2"

    def test_overwrite_across_flushes(self):
        s = LSMStore()
        s.put("k", "old")
        s.flush()
        s.put("k", "new")
        s.flush()
        assert s.get("k") == "new"


class TestCompaction:
    def test_compact_basic(self):
        s = LSMStore()
        s.put("a", "1")
        s.put("b", "2")
        s.flush()
        s.compact()
        assert s.get("a") == "1"
        assert s.get("b") == "2"

    def test_compact_merges_multiple_l0(self):
        s = LSMStore()
        s.put("a", "1")
        s.flush()
        s.put("b", "2")
        s.flush()
        s.compact()
        assert s.get("a") == "1"
        assert s.get("b") == "2"

    def test_compact_newer_wins(self):
        """Later flush overwrites earlier flush for same key."""
        s = LSMStore()
        s.put("k", "old")
        s.flush()
        s.put("k", "new")
        s.flush()
        s.compact()
        assert s.get("k") == "new"

    def test_delete_survives_compaction(self):
        """
        Core correctness: a deleted key must remain deleted after compaction.

        Sequence of events:
          1. put("key", "value") → MemTable
          2. flush()             → L0 SSTable A: {key: value}
          3. compact()           → L1 SSTable:   {key: value}   (A merged into L1)
          4. delete("key")       → MemTable: {key: TOMBSTONE}
          5. flush()             → L0 SSTable B: {key: TOMBSTONE}
          6. compact()           → merge B into L1

        During step 6, the tombstone in B must shadow the value in L1.
        If the compaction drops the tombstone instead of keeping it,
        the merged L1 still contains {key: value} and get("key") returns
        "value" — a deleted key appears to be alive.

        The fix: during compaction, tombstones must be preserved in the
        merged output whenever lower levels might still contain the key.
        Only drop tombstones when compacting the bottommost level where
        no older data can exist.
        """
        s = LSMStore()
        s.put("key", "value")
        s.flush()
        s.compact()                        # value now in L1

        s.delete("key")
        s.flush()                          # tombstone now in L0
        s.compact()                        # tombstone must shadow L1 value

        result = s.get("key")
        assert result is None, (
            f"get('key') returned {result!r} after delete + compaction. "
            "The tombstone was discarded during compaction, allowing the "
            "stale L1 value to become visible again. "
            "Tombstones must be preserved in the merged output when the "
            "compacted level is not the bottommost level."
        )

    def test_delete_then_reinsert_after_compaction(self):
        """Delete then reinsert must work correctly across compactions."""
        s = LSMStore()
        s.put("k", "v1")
        s.flush()
        s.compact()

        s.delete("k")
        s.flush()
        s.compact()

        s.put("k", "v2")
        assert s.get("k") == "v2"

    def test_multiple_keys_some_deleted(self):
        """Non-deleted keys must still be accessible after compaction."""
        s = LSMStore()
        s.put("keep", "yes")
        s.put("drop", "no")
        s.flush()
        s.compact()

        s.delete("drop")
        s.flush()
        s.compact()

        assert s.get("keep") == "yes"
        assert s.get("drop") is None

    def test_compact_twice_delete_persists(self):
        """Tombstone must outlive multiple compactions."""
        s = LSMStore()
        s.put("k", "v")
        s.flush()
        s.compact()

        s.delete("k")
        s.flush()
        s.compact()

        # A second compaction on an empty L0 should not resurrect the key
        s.put("other", "x")
        s.flush()
        s.compact()

        assert s.get("k") is None
        assert s.get("other") == "x"

    def test_three_level_zero_sstables_with_delete(self):
        s = LSMStore()
        s.put("a", "1")
        s.flush()
        s.put("b", "2")
        s.flush()
        s.put("a", "updated")
        s.flush()
        s.compact()

        s.delete("b")
        s.flush()
        s.compact()

        assert s.get("a") == "updated"
        assert s.get("b") is None
