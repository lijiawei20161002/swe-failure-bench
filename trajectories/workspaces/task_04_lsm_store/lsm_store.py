"""
LSM-tree (Log-Structured Merge-Tree) key-value store.

Writes go to an in-memory MemTable. When the MemTable fills up it is
flushed to an immutable SSTable on "disk" (simulated in memory here).
SSTables accumulate in level 0. A compaction merges level-0 SSTables
into level 1, and level-1 SSTables into level 2, etc.

Deletions are recorded as tombstones — a special sentinel value that
means "this key is deleted". Tombstones must shadow older copies of the
same key in lower levels.

Public API:
    store = LSMStore()
    store.put("k", "v")
    store.delete("k")
    store.flush()          # flush MemTable → new level-0 SSTable
    store.compact(level)   # merge level-N SSTables into level N+1
    store.get("k")         # → value or None
"""

from __future__ import annotations

from typing import Any

TOMBSTONE = object()   # sentinel for deleted keys


class SSTable:
    """
    An immutable, sorted sequence of (key, value) pairs.
    value is TOMBSTONE for deleted keys.
    """
    def __init__(self, entries: list[tuple[str, Any]]):
        # entries must be sorted by key, newest-write-wins within the table
        self._data: dict[str, Any] = dict(entries)
        self._keys: list[str] = sorted(self._data)

    def get(self, key: str) -> Any:
        """Return value, TOMBSTONE, or KeyError if key not present."""
        if key in self._data:
            return self._data[key]
        raise KeyError(key)

    def items(self) -> list[tuple[str, Any]]:
        return [(k, self._data[k]) for k in self._keys]

    def __len__(self) -> int:
        return len(self._data)


class LSMStore:
    """
    A simplified LSM-tree store with two levels (0 and 1).

    Level 0 holds recently flushed SSTables (multiple, unsorted relative
    to each other).  Level 1 holds the compacted SSTable.
    """

    def __init__(self):
        self._memtable: dict[str, Any] = {}      # key → value or TOMBSTONE
        self._levels: list[list[SSTable]] = [[], []]  # level 0, level 1

    # ── writes ────────────────────────────────────────────────────────────────

    def put(self, key: str, value: Any) -> None:
        """Insert or update a key."""
        self._memtable[key] = value

    def delete(self, key: str) -> None:
        """Mark a key as deleted (tombstone)."""
        self._memtable[key] = TOMBSTONE

    def flush(self) -> None:
        """Flush the MemTable to a new level-0 SSTable and clear it."""
        if not self._memtable:
            return
        entries = sorted(self._memtable.items())
        self._levels[0].append(SSTable(entries))
        self._memtable.clear()

    # ── compaction ────────────────────────────────────────────────────────────

    def compact(self, level: int = 0) -> None:
        """
        Merge all SSTables at *level* into a single SSTable at *level+1*.

        During a merge, newer entries win over older ones for the same key.
        Within level 0, later SSTables (higher index) are newer.
        Level 1 is older than level 0.
        """
        src = self._levels[level]
        if not src:
            return

        # Build merged view: level+1 base (oldest) then level entries
        # from oldest to newest so later writes overwrite earlier ones.
        merged: dict[str, Any] = {}

        # Start with existing level+1 data (oldest)
        for sst in self._levels[level + 1]:
            for key, value in sst.items():
                merged[key] = value

        # Overlay level data, oldest SSTable first (index 0 is oldest)
        for sst in src:
            for key, value in sst.items():
                merged[key] = value

        # Drop tombstones only when compacting into the bottommost level,
        # where no older data can exist below.
        is_bottom = (level + 1) >= len(self._levels) - 1
        if is_bottom:
            merged = {k: v for k, v in merged.items() if v is not TOMBSTONE}

        self._levels[level] = []
        if merged:
            self._levels[level + 1] = [SSTable(sorted(merged.items()))]
        else:
            self._levels[level + 1] = []

    # ── reads ─────────────────────────────────────────────────────────────────

    def get(self, key: str) -> Any:
        """
        Return the current value for *key*, or None if deleted/absent.

        Search order: MemTable → level 0 (newest first) → level 1.
        A tombstone at any level means the key is deleted.
        """
        # Check MemTable first
        if key in self._memtable:
            val = self._memtable[key]
            return None if val is TOMBSTONE else val

        # Check level 0, newest SSTable first
        for sst in reversed(self._levels[0]):
            try:
                val = sst.get(key)
                return None if val is TOMBSTONE else val
            except KeyError:
                pass

        # Check level 1
        for sst in self._levels[1]:
            try:
                val = sst.get(key)
                return None if val is TOMBSTONE else val
            except KeyError:
                pass

        return None
