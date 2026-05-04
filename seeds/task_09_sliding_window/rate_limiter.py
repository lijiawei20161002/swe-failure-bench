"""
Sliding-window log rate limiter with injectable clock.

A request at time t is within the window [now - window, now]: it is valid
as long as `now - t <= window` (i.e., t >= now - window).  Requests with
t < now - window are expired and removed before each check.

Based on the algorithm used in production API gateways (NGINX limit_req,
Redis ZADD/ZRANGEBYSCORE pattern).

Public API:
    limiter = RateLimiter(limit=5, window=60.0)
    allowed = limiter.is_allowed("user:42")

    # Testing with controlled time:
    clock = lambda: t   # controlled float
    limiter = RateLimiter(limit=5, window=60.0, clock=clock)
"""

from __future__ import annotations

import time
import threading
from collections import deque
from typing import Callable, Dict


class RateLimiter:
    def __init__(
        self,
        limit: int,
        window: float,
        clock: Callable[[], float] | None = None,
    ):
        if limit <= 0:
            raise ValueError("limit must be > 0")
        if window <= 0:
            raise ValueError("window must be > 0")
        self._limit = limit
        self._window = window
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._log: Dict[str, deque] = {}

    def is_allowed(self, key: str) -> bool:
        """
        Return True if the key is within the rate limit.

        Window convention: closed interval [now - window, now].
        A timestamp t is expired when t < now - window (strictly less than).
        Only expired timestamps (t < cutoff) are removed.

        BUG A: the cleanup loop uses `<= cutoff` instead of `< cutoff`,
        removing requests that are exactly at the window boundary (t == cutoff).
        These requests are still IN the window and must NOT be removed.
        """
        now = self._clock()
        cutoff = now - self._window
        with self._lock:
            if key not in self._log:
                self._log[key] = deque()
            log = self._log[key]

            # BUG A: should be `log[0] < cutoff` (strictly less than)
            while log and log[0] <= cutoff:   # BUG A
                log.popleft()

            if len(log) >= self._limit:
                return False

            log.append(now)
            return True

    def remaining(self, key: str) -> int:
        """Return remaining capacity right now."""
        now = self._clock()
        cutoff = now - self._window
        with self._lock:
            if key not in self._log:
                return self._limit
            # BUG A propagates: should count t >= cutoff
            count = sum(1 for t in self._log[key] if t > cutoff)   # BUG A: should be t >= cutoff
            return max(0, self._limit - count)

    def reset(self, key: str) -> None:
        with self._lock:
            self._log.pop(key, None)

    def reset_all(self) -> None:
        with self._lock:
            self._log.clear()


class SlidingWindowCounter(RateLimiter):
    """
    Approximate sliding window using two fixed buckets.

    Weight of previous bucket = fraction of it still in the window =
    1 - elapsed/window, where elapsed is how far into the current bucket we are.

    BUG B: uses `elapsed/window` (inverted), so the previous bucket's weight
    is HIGHEST when we just rotated (should be lowest) and LOWEST near the
    end of the current bucket (should be highest near start, zero near end).
    """

    def __init__(self, limit: int, window: float,
                 clock: Callable[[], float] | None = None):
        super().__init__(limit, window, clock)
        self._current_count: Dict[str, int] = {}
        self._prev_count: Dict[str, int] = {}
        self._bucket_start: Dict[str, float] = {}

    def is_allowed(self, key: str) -> bool:
        now = self._clock()
        with self._lock:
            if key not in self._bucket_start:
                self._bucket_start[key] = now
                self._current_count[key] = 0
                self._prev_count[key] = 0

            elapsed = now - self._bucket_start[key]
            if elapsed >= self._window:
                self._prev_count[key] = self._current_count[key]
                self._current_count[key] = 0
                self._bucket_start[key] = now
                elapsed = 0.0

            # BUG B: inverted — should be (1 - elapsed/window)
            weight = elapsed / self._window
            estimated = (self._prev_count.get(key, 0) * weight
                         + self._current_count.get(key, 0))

            if estimated >= self._limit:
                return False

            self._current_count[key] = self._current_count.get(key, 0) + 1
            return True
