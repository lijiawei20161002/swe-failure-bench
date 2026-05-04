"""
O(1) LFU (Least Frequently Used) cache.

Eviction policy:
  - When the cache is full and a new key is inserted, the *least frequently used*
    key is evicted.
  - Among keys with equal frequency, the *least recently used* one is evicted
    (oldest access, not oldest insertion — access moves a key to "most recent").
  - Accessing a key via get() or updating it via put() increments its frequency.

Based on the algorithm from:
  "An O(1) algorithm for implementing the LFU cache eviction scheme"
  — Shah, Mitra & Matani (2010)

Public API:
    cache = LFUCache(capacity=3)
    cache.put(1, "a")
    cache.get(1)      # → "a"  (freq of key 1 is now 2)
    cache.get(99)     # → -1   (miss)
"""

from __future__ import annotations

from collections import OrderedDict


class LFUCache:
    def __init__(self, capacity: int):
        if capacity <= 0:
            raise ValueError("capacity must be > 0")
        self._cap = capacity
        self._vals: dict = {}                              # key → value
        self._freq: dict = {}                              # key → frequency
        self._freq_to_keys: dict[int, OrderedDict] = {}   # freq → OrderedDict{key: None}
        self._min_freq = 0

    # ── public API ────────────────────────────────────────────────────────────

    def get(self, key) -> object:
        """Return cached value or -1 on miss."""
        if key not in self._vals:
            return -1
        self._increment(key)
        return self._vals[key]

    def put(self, key, value) -> None:
        """Insert or update key. Evicts LFU/LRU key when at capacity."""
        if key in self._vals:
            self._vals[key] = value
            self._increment(key)
            return

        if len(self._vals) >= self._cap:
            self._evict()

        self._vals[key] = value
        self._freq[key] = 1
        if 1 not in self._freq_to_keys:
            self._freq_to_keys[1] = OrderedDict()
        self._freq_to_keys[1][key] = None
        self._min_freq = 1

    # ── internals ─────────────────────────────────────────────────────────────

    def _increment(self, key) -> None:
        f = self._freq[key]
        del self._freq_to_keys[f][key]
        if not self._freq_to_keys[f]:
            del self._freq_to_keys[f]
            if f == self._min_freq:
                self._min_freq += 1

        new_f = f + 1
        self._freq[key] = new_f
        if new_f not in self._freq_to_keys:
            self._freq_to_keys[new_f] = OrderedDict()
        self._freq_to_keys[new_f][key] = None

    def _evict(self) -> None:
        """Evict the LFU key; break ties by LRU (oldest access first)."""
        bucket = self._freq_to_keys[self._min_freq]
        evict_key, _ = bucket.popitem(last=False)          # pop LRU = first item
        if not bucket:
            del self._freq_to_keys[self._min_freq]
        del self._vals[evict_key]
        del self._freq[evict_key]

    # ── introspection (for tests) ─────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self._vals)

    def __contains__(self, key) -> bool:
        return key in self._vals

    def frequency(self, key) -> int:
        """Return the access frequency of *key*, or 0 if not in cache."""
        return self._freq.get(key, 0)
