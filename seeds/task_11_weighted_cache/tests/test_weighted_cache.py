"""Tests for WeightedLRUCache. Run: pytest tests/ -x"""
import pytest
from weighted_cache import WeightedLRUCache


# ── basic get/put ─────────────────────────────────────────────────────────────

class TestBasic:
    def test_put_and_get(self):
        c = WeightedLRUCache(max_size=100)
        c.put("a", "hello", size=10)
        assert c.get("a") == "hello"

    def test_miss_returns_none(self):
        c = WeightedLRUCache(max_size=100)
        assert c.get("missing") is None

    def test_total_size_tracked(self):
        c = WeightedLRUCache(max_size=100)
        c.put("a", 1, size=30)
        c.put("b", 2, size=20)
        assert c.total_size == 50

    def test_free_space(self):
        c = WeightedLRUCache(max_size=100)
        c.put("a", 1, size=30)
        assert c.free_space == 70

    def test_invalid_max_size(self):
        with pytest.raises(ValueError):
            WeightedLRUCache(max_size=0)

    def test_item_too_large(self):
        c = WeightedLRUCache(max_size=10)
        with pytest.raises(ValueError):
            c.put("big", "data", size=11)


# ── eviction ──────────────────────────────────────────────────────────────────

class TestEviction:
    def test_evicts_lru_when_full(self):
        """When inserting a new item would exceed max_size, evict LRU first."""
        c = WeightedLRUCache(max_size=10)
        c.put("a", 1, size=6)
        c.put("b", 2, size=6)   # should evict "a" to fit
        assert c.get("a") is None, "a should be evicted (LRU)"
        assert c.get("b") == 2

    def test_evicts_multiple_lru_until_fit(self):
        """May need to evict several entries to fit a large new item."""
        c = WeightedLRUCache(max_size=10)
        c.put("a", 1, size=4)
        c.put("b", 2, size=4)
        c.put("c", 3, size=7)   # must evict a and b to fit 7 into 10
        assert c.get("a") is None
        assert c.get("b") is None
        assert c.get("c") == 3
        assert c.total_size == 7

    def test_get_refreshes_lru_order(self):
        """get() moves the key to MRU; a different key should be evicted."""
        c = WeightedLRUCache(max_size=10)
        c.put("a", 1, size=5)
        c.put("b", 2, size=5)
        c.get("a")              # refresh a → b is now LRU
        c.put("c", 3, size=5)  # must evict b (LRU)
        assert c.get("b") is None, "b should be evicted (LRU after a was refreshed)"
        assert c.get("a") == 1
        assert c.get("c") == 3

    def test_total_size_after_eviction(self):
        c = WeightedLRUCache(max_size=10)
        c.put("a", 1, size=6)
        c.put("b", 2, size=6)  # evicts a
        assert c.total_size == 6, (
            f"After eviction total_size should be 6, got {c.total_size}"
        )

    def test_size_exactly_at_max_allows_new(self):
        """When cache is exactly at max_size, inserting something that would
        push it over must trigger eviction first."""
        c = WeightedLRUCache(max_size=10)
        c.put("a", 1, size=10)  # exactly full
        c.put("b", 2, size=1)   # needs 1 free unit → must evict a
        assert c.get("a") is None
        assert c.get("b") == 2


# ── update existing key ───────────────────────────────────────────────────────

class TestUpdate:
    def test_update_same_size_correct_total(self):
        c = WeightedLRUCache(max_size=100)
        c.put("a", "v1", size=20)
        c.put("a", "v2", size=20)
        assert c.get("a") == "v2"
        assert c.total_size == 20, f"Expected 20, got {c.total_size}"

    def test_update_larger_size(self):
        """Updating with a larger size should increase total_size correctly."""
        c = WeightedLRUCache(max_size=100)
        c.put("a", "v1", size=10)
        c.put("b", "v2", size=20)
        c.put("a", "v3", size=30)  # update: was 10, now 30 → delta +20
        assert c.total_size == 50, (
            f"total_size should be 50 (30+20), got {c.total_size}"
        )

    def test_update_smaller_size(self):
        """Updating with a smaller size should decrease total_size."""
        c = WeightedLRUCache(max_size=100)
        c.put("a", "v1", size=40)
        c.put("a", "v2", size=10)
        assert c.total_size == 10, (
            f"total_size should be 10 after shrinking from 40 to 10, got {c.total_size}"
        )

    def test_update_triggers_eviction_if_needed(self):
        """If updating causes total to exceed max, evict others."""
        c = WeightedLRUCache(max_size=20)
        c.put("a", 1, size=10)
        c.put("b", 2, size=10)  # full
        c.put("a", 3, size=15)  # update a from 10→15; total would be 25 > 20 → evict b
        assert c.get("b") is None, "b should be evicted to make room for larger a"
        assert c.get("a") == 3
        assert c.total_size == 15


# ── evict_to_fit ──────────────────────────────────────────────────────────────

class TestEvictToFit:
    def test_evict_to_fit_basic(self):
        c = WeightedLRUCache(max_size=100)
        c.put("a", 1, size=40)
        c.put("b", 2, size=40)
        n = c.evict_to_fit(30)
        assert n == 1, "Should evict exactly one entry"
        assert c.free_space >= 30

    def test_evict_to_fit_already_enough_space(self):
        c = WeightedLRUCache(max_size=100)
        c.put("a", 1, size=10)
        n = c.evict_to_fit(30)
        assert n == 0, "No eviction needed"
