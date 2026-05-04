# Task: Fix O(1) LFU Cache

## User Persona

- **High-level goals:** Replacing an LRU cache with an LFU cache in a CDN edge node. Needs correct eviction semantics and O(1) time complexity for get/put.
- **Familiarity with tools:** Senior engineer who has implemented LRU before. Has read the Shah–Mitra–Matani LFU paper. Knows about the frequency-bucket approach. Will notice if the eviction is O(n).
- **Communication style:** Focused on correctness of eviction order. Will write out exactly what keys/frequencies the cache should have at each step.
- **Patience style:** Very precise. Will catch incorrect tie-breaking immediately.
- **Hint policy:** Will mention the frequency-bucket data structure if the agent is using sorted() or iteration. Will not write code.

## Context

Implementation: `lfu_cache.py`. Tests: `tests/test_lfu_cache.py`.

```bash
cd /workspace && pip install pytest --quiet && pytest tests/ -x -q 2>&1 | tail -30
```

## Milestones

### Milestone 1: Fix Eviction — Correct Minimum Frequency Tracking

**Initial Prompt:**

> "I have an LFU cache implementation in `lfu_cache.py`. The eviction order is wrong. When I insert more keys than capacity, it's not evicting the least-frequently-used key correctly. The test `test_evicts_least_frequent` in `TestEviction` shows the problem. The implementation uses a `_freq_to_keys` dict mapping frequency → OrderedDict of keys — that structure is right, but `_min_freq` is never updated correctly. Fix it so eviction picks the right key."

**Planned Interactions:**

- Clarification answers:
  - If agent asks what "correct" means: "The least-frequently-used key is evicted. Among equal-frequency keys, the oldest-inserted (LRU) one is evicted."
  - If agent asks about the O(1) requirement: "Yes, both get() and put() must be O(1). No sorting, no iteration over all keys."
- Corrections and hints:
  - If agent fixes eviction but uses `min(self._freq_to_keys)`: "That's O(n) — you're iterating all frequency buckets. The point of `_min_freq` is to avoid that. Track it properly."
  - If agent sets `_min_freq = 1` in put() but not in `_increment()`: "`test_new_key_min_freq_resets` still fails — after eviction and a new insert, subsequent increments don't update `_min_freq` correctly."

**Completion Criteria:**

`pytest tests/test_lfu_cache.py::TestEviction -x -q` passes.

---

### Milestone 2: Fix LRU Tie-Breaking Within Frequency Buckets

**Initial Prompt:**

> "Eviction picks the right frequency now, but it's evicting the wrong key when two keys have the same frequency. It should evict the *least recently used* one (i.e., the one inserted into that frequency bucket earliest). Look at `test_lru_tiebreak` and `test_lru_tiebreak_after_access`."

**Planned Interactions:**

- Clarification answers:
  - If agent asks which comes first in `_freq_to_keys[f]`: "`_freq_to_keys[f]` is an `OrderedDict` — the first key in it is the LRU one (inserted first). `_evict()` should pop the first key."
- Corrections and hints:
  - If agent uses `sorted()` for tie-breaking: "That gives alphabetical order, not insertion order. Use `next(iter(ordered_dict))` to get the oldest."
  - If `get()` doesn't move the key to end of its frequency bucket: "`test_lru_tiebreak_after_access` still fails — when you call `get()`, the key should move to the 'most recently used' position in the new frequency bucket."

**Completion Criteria:**

`pytest tests/test_lfu_cache.py::TestEviction tests/test_lfu_cache.py::TestFrequency -x -q` passes.

---

### Milestone 3: Full Test Suite

**Initial Prompt:**

> "Now run the full test suite and fix anything remaining. Pay attention to `TestStress` — it verifies that after sequential insertions only the most recently inserted keys survive."

**Planned Interactions:**

- Corrections and hints:
  - If stress tests fail due to frequency mis-tracking: "Check that `put()` on an existing key increments frequency and updates `_min_freq` if needed."

**Completion Criteria:**

`pytest tests/ -x -q` passes all tests.
