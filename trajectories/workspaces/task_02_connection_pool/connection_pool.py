"""
Thread-safe database connection pool.

Modelled after psycopg2-pool / redis-py ConnectionPool patterns.

Public API:
    pool = ConnectionPool(factory=create_conn, max_size=10, timeout=5.0)
    conn = pool.acquire()   # blocks until a connection is available
    pool.release(conn)      # return connection; closes it if pool is full
    pool.close()            # close all idle connections, reject new acquire()
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable


class PoolExhaustedError(Exception):
    """Raised when acquire() times out waiting for a free connection."""


class PoolClosedError(Exception):
    """Raised when acquire() is called on a closed pool."""


class ConnectionPool:
    def __init__(
        self,
        factory: Callable[[], Any],
        max_size: int = 10,
        timeout: float = 5.0,
    ):
        self._factory = factory
        self._max_size = max_size
        self._timeout = timeout

        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)
        self._idle: list[Any] = []
        self._in_use: int = 0
        self._in_use_set: set[Any] = set()
        self._closed = False

    # ── acquire ──────────────────────────────────────────────────────────────

    def acquire(self) -> Any:
        deadline = time.monotonic() + self._timeout

        with self._not_empty:
            while True:
                if self._closed:
                    raise PoolClosedError("pool is closed")

                # Return an idle connection if one exists
                if self._idle:
                    conn = self._idle.pop()
                    self._in_use += 1
                    self._in_use_set.add(conn)
                    return conn

                # Spin up a new connection if under limit
                total = len(self._idle) + self._in_use
                if total < self._max_size:
                    conn = self._factory()
                    self._in_use += 1
                    self._in_use_set.add(conn)
                    return conn

                # Wait for a connection to become available
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise PoolExhaustedError(
                        f"no connection available after {self._timeout}s"
                    )
                self._not_empty.wait(timeout=remaining)

    # ── release ──────────────────────────────────────────────────────────────

    def release(self, conn: Any) -> None:
        """Return a connection to the pool."""
        with self._not_empty:
            if conn not in self._in_use_set:
                raise ValueError("connection not acquired from this pool or already released")
            self._in_use_set.remove(conn)
            self._in_use -= 1
            if self._closed:
                _close_conn(conn)
                self._not_empty.notify()
                return
            # Keep idle if under limit, otherwise discard
            if len(self._idle) + self._in_use < self._max_size:
                self._idle.append(conn)
            else:
                _close_conn(conn)
            self._not_empty.notify()

    # ── close ─────────────────────────────────────────────────────────────────

    def close(self) -> None:
        """Close all idle connections and prevent new acquire() calls."""
        with self._not_empty:
            self._closed = True
            idle = self._idle[:]
            self._idle.clear()
            self._not_empty.notify_all()
        for c in idle:
            _close_conn(c)

    @property
    def size(self) -> int:
        """Total connections managed by this pool (idle + in-use)."""
        with self._lock:
            return len(self._idle) + self._in_use

    @property
    def idle_count(self) -> int:
        with self._lock:
            return len(self._idle)


def _close_conn(conn: Any) -> None:
    """Best-effort close."""
    close = getattr(conn, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass
