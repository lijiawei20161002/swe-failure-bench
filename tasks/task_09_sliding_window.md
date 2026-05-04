# Task: Fix Sliding-Window Rate Limiter

## User Persona

- **High-level goals:** Shipping a rate limiter for a public API. It needs to correctly count requests in a sliding window — not a fixed window.
- **Familiarity with tools:** Senior engineer who has read NGINX's rate-limit docs and understands the difference between fixed-window and sliding-window approaches. Knows what "window boundary" means and will test edge cases.
- **Opinions on patterns:** Prefers the log-based approach for exactness over approximate counter approaches.
- **Communication style:** Precise. Describes bug with exact timestamps: "a request at t=0 should still count at now=60 with a 60s window."
- **Patience style:** Will give one correction per bug. Won't give hints about which line is wrong.
- **Hint policy:** Will not suggest specific fixes. Will only describe observable behavior.

## Context

Implementation: `rate_limiter.py`. Tests: `tests/test_rate_limiter.py`.

```bash
cd /workspace && pip install pytest --quiet && pytest tests/ -x -q 2>&1 | tail -30
```

## Milestones

### Milestone 1: Fix the Log-Based Rate Limiter (RateLimiter class)

**Initial Prompt:**

> "My sliding-window rate limiter has a bug with boundary handling. If I make 2 requests at t=0 with a 60s window (limit=2), then at exactly t=60 I try a 3rd — it should be denied because the first two are still in the window [0, 60]. But it's being allowed instead. Look at `rate_limiter.py` and fix it. Tests are in `TestWindowExpiry`."

**Planned Interactions:**

- Clarification answers:
  - If agent asks about window convention: "The window is a closed interval [now - window, now]. A request exactly at the boundary is still in the window."
  - If agent asks which method: "Look at the cleanup loop in `is_allowed()` and the `remaining()` method."
- Corrections and hints:
  - If agent changes cleanup but `remaining()` still wrong: "The `remaining()` test still fails — make sure it's consistent with `is_allowed()`."

**Completion Criteria:**

`pytest tests/test_rate_limiter.py::TestWindowExpiry -x -q` passes all tests.

---

### Milestone 2: Fix the SlidingWindowCounter

**Initial Prompt:**

> "Now fix `SlidingWindowCounter`. Right after rotating buckets, requests from the previous bucket should all count with full weight (weight=1.0). But my test shows they're being completely ignored immediately after rotation. The weight formula is wrong. Fix it. See `TestSlidingWindowCounter`."

**Planned Interactions:**

- Clarification answers:
  - If agent asks about the weight formula: "The previous bucket's contribution should decrease linearly as the current bucket fills. At elapsed=0 it should be 100% of the previous count; at elapsed=window it should be 0%."
- Corrections and hints:
  - If agent changes the formula but gets the direction wrong: "The test `test_prev_bucket_low_weight_near_end` still fails — at 95% through the window, old requests should contribute very little."

**Completion Criteria:**

`pytest tests/ -x -q` passes all tests.
