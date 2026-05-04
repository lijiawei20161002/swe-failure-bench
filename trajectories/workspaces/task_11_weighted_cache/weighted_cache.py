"""
Size-aware LRU cache.

Each cached value has an associated `size`. The cache evicts LRU entries
until the total stored size is at or below `max_size` before inserting a new
entry.

Based on patterns used in content-delivery caches, browser caches (e.g.,
HTTP response cache with Content-Length), and in-process slab allocators.

Public API:
    cache = WeightedLRUCache(max_size=1000)
    cache.put("img1", image_bytes, size=256)
    data = cache.get("img1")    # bytes or None on miss
    cache.evict_to_fit(200)     # ensure 200 units of free space
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any


class WeightedLRUCache:
    def __init__(self, max_size: int):
        if max_size <= 0:
            raise ValueError("max_size must be > 0")
        self._max_size = max_size
        self._cache: OrderedDict[str, tuple[Any, int]] = OrderedDict()
        self._total_size = 0

    # ── public API ────────────────────────────────────────────────────────────

    def get(self, key: str) -> Any | None:
        if key not in self._cache:
            return None
        self._cache.move_to_end(key)
        return self._cache[key][0]

    def put(self, key: str, value: Any, *, size: int) -> None:
        if size <= 0:
            raise ValueError("size must be > 0")
        if size > self._max_size:
            raise ValueError(f"item size {size} exceeds max_size {self._max_size}")

        if key in self._cache:
            # Remove the old entry so we can re-insert it as MRU and
            # correctly account for any size change.
            old_size = self._cache.pop(key)[1]
            self._total_size -= old_size

        # Evict LRU entries until there is room for the new item.
        while self._total_size + size > self._max_size and self._cache:
            _, (_, evicted_size) = self._cache.popitem(last=False)
            self._total_size -= evicted_size

        self._cache[key] = (value, size)
        self._total_size += size

    def evict_to_fit(self, needed: int) -> int:
        """
        Evict LRU entries until at least `needed` units of free space are
        available. Returns number of entries evicted.
        """
        evicted = 0
        while self.free_space < needed and self._cache:
            _, (_, sz) = self._cache.popitem(last=False)
            self._total_size -= sz
            evicted += 1
        return evicted

    # ── properties ────────────────────────────────────────────────────────────

    @property
    def total_size(self) -> int:
        return self._total_size

    @property
    def free_space(self) -> int:
        return self._max_size - self._total_size

    def __len__(self) -> int:
        return len(self._cache)

    def __contains__(self, key: str) -> bool:
        return key in self._cache
