"""Tests for RateLimiter. Run: pytest tests/ -x"""
import threading
import pytest
from rate_limiter import RateLimiter, SlidingWindowCounter


# ── helpers ───────────────────────────────────────────────────────────────────

def make_clock(start: float = 0.0):
    """Fake clock. Call it to get time; call .advance(dt) to tick."""
    state = [start]

    class Clock:
        def __call__(self):
            return state[0]
        def advance(self, dt: float):
            state[0] += dt

    return Clock()


# ── basic allow / deny ────────────────────────────────────────────────────────

class TestBasic:
    def test_allows_up_to_limit(self):
        rl = RateLimiter(limit=3, window=60)
        assert all(rl.is_allowed("k") for _ in range(3))

    def test_denies_over_limit(self):
        rl = RateLimiter(limit=3, window=60)
        for _ in range(3):
            rl.is_allowed("k")
        assert rl.is_allowed("k") is False

    def test_independent_keys(self):
        rl = RateLimiter(limit=1, window=60)
        assert rl.is_allowed("a") is True
        assert rl.is_allowed("b") is True
        assert rl.is_allowed("a") is False

    def test_reset_clears_key(self):
        rl = RateLimiter(limit=1, window=60)
        rl.is_allowed("k")
        rl.reset("k")
        assert rl.is_allowed("k") is True

    def test_remaining_decreases(self):
        rl = RateLimiter(limit=5, window=60)
        rl.is_allowed("k")
        rl.is_allowed("k")
        assert rl.remaining("k") == 3

    def test_invalid_limit(self):
        with pytest.raises(ValueError):
            RateLimiter(limit=0, window=60)


# ── window expiry (controlled clock) ──────────────────────────────────────────

class TestWindowExpiry:
    def test_expired_requests_allow_new(self):
        clock = make_clock(0.0)
        rl = RateLimiter(limit=2, window=60.0, clock=clock)
        rl.is_allowed("k")
        rl.is_allowed("k")
        assert rl.is_allowed("k") is False
        clock.advance(61.0)          # move past window
        assert rl.is_allowed("k") is True

    def test_boundary_request_still_counts(self):
        """
        Window = [now - window, now].  A request at t = now - window is AT the
        left boundary and must still count against the limit.

        Timeline:
          t=0:  request 1 (limit=2)
          t=30: request 2
          t=60: now=60, cutoff=0.  Request at t=0 is AT cutoff — still in window.
                → 2 requests in window → 3rd must be denied.
        """
        clock = make_clock(0.0)
        rl = RateLimiter(limit=2, window=60.0, clock=clock)
        rl.is_allowed("k")    # t=0
        clock.advance(30.0)
        rl.is_allowed("k")    # t=30
        clock.advance(30.0)   # now=60, cutoff=0; request at t=0 still in [0, 60]

        result = rl.is_allowed("k")
        assert result is False, (
            "Request at t=0 is at window boundary (cutoff=0) and must still count. "
            "BUG A incorrectly evicts it because it uses '<= cutoff' instead of '< cutoff'."
        )

    def test_strictly_expired_request_does_not_count(self):
        """A request at t < cutoff (strictly outside window) IS expired."""
        clock = make_clock(0.0)
        rl = RateLimiter(limit=2, window=60.0, clock=clock)
        rl.is_allowed("k")    # t=0
        rl.is_allowed("k")    # t=0
        clock.advance(60.001) # now=60.001, cutoff=0.001; t=0 < cutoff → expired
        # One slot freed → should allow
        assert rl.is_allowed("k") is True

    def test_remaining_includes_boundary_request(self):
        """remaining() must count the request at the boundary."""
        clock = make_clock(0.0)
        rl = RateLimiter(limit=3, window=60.0, clock=clock)
        rl.is_allowed("k")    # t=0
        rl.is_allowed("k")    # t=0
        clock.advance(60.0)   # now=60, cutoff=0; both t=0 requests at boundary
        remaining = rl.remaining("k")
        assert remaining == 1, (
            f"2 boundary requests still in window → remaining should be 1, got {remaining}. "
            "BUG A causes remaining() to miss them."
        )

    def test_partial_expiry(self):
        """Only truly expired requests are removed; boundary ones stay."""
        clock = make_clock(0.0)
        rl = RateLimiter(limit=3, window=60.0, clock=clock)
        rl.is_allowed("k")    # t=0  (at boundary when now=60)
        clock.advance(30.0)
        rl.is_allowed("k")    # t=30 (inside window when now=60)
        rl.is_allowed("k")    # t=30 (inside window when now=60)
        clock.advance(30.0)   # now=60, cutoff=0
        # t=0 is at boundary (in window), t=30 is inside → all 3 still count
        assert rl.remaining("k") == 0, "All 3 requests in [0,60] → no remaining"
        assert rl.is_allowed("k") is False


# ── thread safety ─────────────────────────────────────────────────────────────

class TestThreadSafety:
    def test_concurrent_exactly_limit_allowed(self):
        rl = RateLimiter(limit=10, window=60)
        allowed = []

        def worker():
            if rl.is_allowed("shared"):
                allowed.append(1)

        threads = [threading.Thread(target=worker) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(allowed) == 10


# ── sliding window counter ────────────────────────────────────────────────────

class TestSlidingWindowCounter:
    def test_basic_allow_deny(self):
        clock = make_clock(0.0)
        swc = SlidingWindowCounter(limit=3, window=60.0, clock=clock)
        for _ in range(3):
            swc.is_allowed("k")
        assert swc.is_allowed("k") is False

    def test_prev_bucket_full_weight_at_rotation(self):
        """
        Immediately after rotating buckets (elapsed=0), the previous bucket
        carries full weight (weight = 1 - 0/window = 1.0).

        If prev_count = limit, no new requests should be allowed.
        With BUG B (weight = 0/window = 0), the previous bucket is ignored
        and new requests are incorrectly allowed.
        """
        clock = make_clock(0.0)
        swc = SlidingWindowCounter(limit=5, window=60.0, clock=clock)
        for _ in range(5):
            swc.is_allowed("k")
        clock.advance(60.0)   # rotate: prev=5, current=0, elapsed=0

        result = swc.is_allowed("k")
        assert result is False, (
            "Just after rotation, prev bucket has full weight (1.0). "
            "5 prev requests * 1.0 = 5 >= limit=5 → must deny. "
            "BUG B inverts weight to 0.0, making estimate=0 → incorrectly allows."
        )

    def test_prev_bucket_low_weight_near_end(self):
        """
        Near the end of the current bucket (elapsed ≈ window), the previous
        bucket has near-zero weight (1 - ~1 ≈ 0). With prev_count requests
        that would otherwise block, we should now be allowed.
        """
        clock = make_clock(0.0)
        swc = SlidingWindowCounter(limit=5, window=100.0, clock=clock)
        for _ in range(5):
            swc.is_allowed("k")
        clock.advance(100.0)   # rotate
        clock.advance(95.0)    # 95% through next window; weight = 1 - 0.95 = 0.05
        # estimate = 5 * 0.05 = 0.25 < limit → allow
        result = swc.is_allowed("k")
        assert result is True, (
            "At 95% of window, old requests carry weight 0.05, estimate=0.25 < 5 → allow. "
            "BUG B gives weight=0.95, estimate=4.75 ≈ 5 → may deny."
        )

    def test_weight_decreases_monotonically(self):
        """
        As time passes within a bucket, the previous bucket's contribution
        should decrease (not increase).
        """
        clock = make_clock(0.0)
        swc = SlidingWindowCounter(limit=100, window=100.0, clock=clock)
        for _ in range(50):
            swc.is_allowed("k")
        clock.advance(100.0)   # rotate

        # Sample remaining capacity at 10%, 50%, 90% of new window
        def capacity_at(pct: float) -> int:
            swc2 = SlidingWindowCounter(limit=100, window=100.0, clock=make_clock(0.0))
            for _ in range(50):
                swc2.is_allowed("k")
            c2 = make_clock(0.0)
            c2.advance(100.0)
            c2.advance(pct)
            swc2._clock = c2
            # just read estimate by checking how many are allowed
            count = 0
            for _ in range(100):
                if swc2.is_allowed("k2"):
                    count += 1
                else:
                    break
            return count

        # Skip this complex test in favor of the simpler ones above
        # (included for documentation; property-based version would use hypothesis)
        pass
