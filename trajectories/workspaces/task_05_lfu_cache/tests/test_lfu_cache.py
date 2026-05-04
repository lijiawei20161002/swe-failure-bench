"""Tests for LFUCache. Run: pytest tests/ -x"""
import pytest
from lfu_cache import LFUCache


# ── basic get / put ───────────────────────────────────────────────────────────

class TestBasic:
    def test_miss_returns_minus_one(self):
        c = LFUCache(2)
        assert c.get("x") == -1

    def test_put_then_get(self):
        c = LFUCache(2)
        c.put("a", 1)
        assert c.get("a") == 1

    def test_update_value(self):
        c = LFUCache(2)
        c.put("a", 1)
        c.put("a", 99)
        assert c.get("a") == 99

    def test_capacity_one(self):
        c = LFUCache(1)
        c.put("a", 1)
        c.put("b", 2)   # evicts "a"
        assert c.get("a") == -1
        assert c.get("b") == 2

    def test_invalid_capacity(self):
        with pytest.raises(ValueError):
            LFUCache(0)


# ── eviction — correct minimum frequency ────────────────────────────────────

class TestEviction:
    def test_evicts_least_frequent(self):
        """Eviction must remove the key with the lowest access count."""
        c = LFUCache(3)
        c.put(1, "one")
        c.put(2, "two")
        c.put(3, "three")
        c.get(1)    # freq(1)=2
        c.get(1)    # freq(1)=3
        c.get(2)    # freq(2)=2
        # freq: 1→3, 2→2, 3→1  → inserting 4 should evict key 3 (lowest freq)
        c.put(4, "four")
        assert c.get(3) == -1, "key 3 (freq=1) should be evicted"
        assert c.get(1) == "one"
        assert c.get(2) == "two"
        assert c.get(4) == "four"

    def test_new_key_min_freq_is_one(self):
        """After inserting a new key, the next eviction must consider it as freq=1."""
        c = LFUCache(2)
        c.put("a", 1)
        c.get("a")          # freq(a)=2
        c.put("b", 2)       # freq(b)=1; _min_freq must be 1, not 0
        # inserting "c" must evict "b" (freq=1), not "a" (freq=2)
        c.put("c", 3)
        assert c.get("b") == -1, "b (freq=1) should be evicted, not a (freq=2)"
        assert c.get("a") == 1
        assert c.get("c") == 3

    def test_min_freq_after_increment(self):
        """After get() increments a key from freq 1→2, the min bucket (1) may become
        empty. _min_freq must be updated so the next eviction is correct."""
        c = LFUCache(2)
        c.put("a", 1)   # freq=1
        c.put("b", 2)   # freq=1
        c.get("a")      # freq(a)=2; both a,b in cache; freq-1 bucket now only has b
        c.get("b")      # freq(b)=2; freq-1 bucket is now EMPTY, min_freq should be 2
        c.put("c", 3)   # must evict one of {a,b} — both at freq=2; evict LRU of those
        # "a" was accessed before "b" (a's last access was get("a"), b's was get("b"))
        # So b is more recently used → a should be evicted
        assert c.get("a") == -1 or c.get("b") == -1, (
            "one of a or b must be evicted; _min_freq must point to freq=2 bucket"
        )
        assert c.get("c") == 3


# ── LRU tie-breaking within a frequency bucket ────────────────────────────────

class TestLRUTieBreak:
    def test_basic_lru_tiebreak(self):
        """Among same-frequency keys, the least-recently-used one is evicted."""
        c = LFUCache(3)
        c.put("x", 1)   # all freq=1; x was accessed first
        c.put("y", 2)
        c.put("z", 3)
        # All have freq=1. "x" is LRU (oldest access). Insert "w" → evict "x".
        c.put("w", 4)
        assert c.get("x") == -1, "x should be evicted (LRU among freq=1)"
        assert c.get("y") == 2
        assert c.get("z") == 3
        assert c.get("w") == 4

    def test_get_makes_key_most_recently_used(self):
        """After get(), the key moves to 'most recently used' position in its new bucket."""
        c = LFUCache(3)
        c.put("a", 1)
        c.put("b", 2)
        c.put("c", 3)
        # All freq=1. Access "a" → freq(a)=2. freq-1 bucket: [b, c]; b is LRU.
        c.get("a")
        # Insert "d" → evict LRU from freq-1, which is "b"
        c.put("d", 4)
        assert c.get("b") == -1, "b should be evicted (LRU in freq-1 after a was promoted)"
        assert c.get("a") == 1
        assert c.get("c") == 3
        assert c.get("d") == 4

    def test_sequential_gets_lru_order(self):
        """Multiple gets create LRU order within the frequency-2 bucket."""
        c = LFUCache(3)
        c.put("p", 10)
        c.put("q", 20)
        c.put("r", 30)
        c.get("p")   # p→freq2
        c.get("q")   # q→freq2; freq-2 bucket: [p, q] with p as LRU
        c.get("r")   # r→freq2; freq-2 bucket: [p, q, r] with p as LRU
        # All freq=2. LRU in freq-2 is "p" (accessed first).
        c.put("s", 40)   # evict p
        assert c.get("p") == -1, "p should be evicted (LRU among freq-2)"
        assert c.get("q") == 20
        assert c.get("r") == 30
        assert c.get("s") == 40


# ── frequency tracking ────────────────────────────────────────────────────────

class TestFrequency:
    def test_initial_frequency_is_one(self):
        c = LFUCache(3)
        c.put("a", 1)
        assert c.frequency("a") == 1

    def test_get_increments_frequency(self):
        c = LFUCache(3)
        c.put("a", 1)
        c.get("a")
        c.get("a")
        assert c.frequency("a") == 3

    def test_put_update_increments_frequency(self):
        c = LFUCache(3)
        c.put("a", 1)
        c.put("a", 2)
        assert c.frequency("a") == 2

    def test_miss_has_zero_frequency(self):
        c = LFUCache(3)
        assert c.frequency("nonexistent") == 0


# ── stress ────────────────────────────────────────────────────────────────────

class TestStress:
    def test_all_same_frequency_evicts_oldest(self):
        """With all keys at freq=1, always the oldest inserted is evicted."""
        c = LFUCache(3)
        # Insert in order: 10, 20, 30, 40, 50
        for k in [10, 20, 30]:
            c.put(k, k)
        c.put(40, 40)   # evicts 10
        assert c.get(10) == -1
        c.put(50, 50)   # evicts 20
        assert c.get(20) == -1
        assert c.get(30) == 30
        assert c.get(40) == 40
        assert c.get(50) == 50

    def test_mixed_frequency_ordering(self):
        """Realistic workload: some keys hot, some cold."""
        c = LFUCache(4)
        c.put("hot1", 1)
        c.put("hot2", 2)
        c.put("cold1", 3)
        c.put("cold2", 4)
        for _ in range(5):
            c.get("hot1")   # freq=6
            c.get("hot2")   # freq=6
        c.put("new", 99)    # evict one of cold1/cold2 (freq=1, cold1 is LRU)
        assert c.get("cold1") == -1, "cold1 should be evicted (LRU among freq=1)"
        assert c.get("hot1") == 1
        assert c.get("hot2") == 2
        assert c.get("new") == 99
