# Task: Fix Size-Aware LRU Cache

## User Persona

- **High-level goals:** Implementing a cache where each entry has a byte-size cost, and the total cached bytes must not exceed a budget. Used for HTTP response caching.
- **Familiarity with tools:** Strong Python developer who has used `OrderedDict` before. Understands that updating a key should replace its size, not add to it.
- **Communication style:** Describes bugs in terms of observed `total_size` values: "After updating key 'a' from size 10 to size 30, total_size is 70 but should be 50."
- **Patience style:** Will escalate after one failed fix. Pastes the exact test output.
- **Hint policy:** Will describe the symptom, not the cause.

## Context

Implementation: `weighted_cache.py`. Tests: `tests/test_weighted_cache.py`.

```bash
cd /workspace && pip install pytest --quiet && pytest tests/ -x -q 2>&1 | tail -30
```

## Milestones

### Milestone 1: Fix Total-Size Tracking on Update

**Initial Prompt:**

> "When I update an existing key with a different size, `total_size` is wrong. If 'a' has size 10, 'b' has size 20, then I update 'a' to size 30, the total should be 50 but I'm getting 70. Look at the `put()` method in `weighted_cache.py`."

**Planned Interactions:**

- Clarification answers:
  - If agent asks what total_size should be: "It should always equal the sum of all current entry sizes. Update must replace, not add."
- Corrections and hints:
  - If agent fixes size tracking but update doesn't trigger eviction: "The test `test_update_triggers_eviction_if_needed` still fails — if updating makes total exceed max_size, it should evict LRU entries."

**Completion Criteria:**

`pytest tests/test_weighted_cache.py::TestUpdate -x -q` passes all 4 tests.

---

### Milestone 2: Fix Eviction Loop Condition

**Initial Prompt:**

> "The eviction isn't making room for the new item. If my cache is at capacity (total_size == max_size) and I insert something new, it inserts without evicting, pushing total_size over max_size. Fix the eviction loop in `put()`."

**Planned Interactions:**

- Clarification answers:
  - If agent asks about the invariant: "After `put()` completes, `total_size` must always be <= `max_size`."
- Corrections and hints:
  - If agent changes condition but still overshoots: "The loop should continue until there's *enough room for the new item*, not just until we're under max_size."

**Completion Criteria:**

`pytest tests/ -x -q` passes all tests.
