"""Tests for ConnectionPool. Run: pytest tests/ -x"""
import threading
import time
import pytest
from connection_pool import ConnectionPool, PoolExhaustedError, PoolClosedError


# ── fake connection ───────────────────────────────────────────────────────────

class FakeConn:
    def __init__(self, n):
        self.id = n
        self.closed = False

    def close(self):
        self.closed = True


_counter = 0
def make_conn():
    global _counter
    _counter += 1
    return FakeConn(_counter)

@pytest.fixture(autouse=True)
def reset_counter():
    global _counter
    _counter = 0
    yield


# ── basic acquire / release ───────────────────────────────────────────────────

class TestBasic:
    def test_acquire_returns_connection(self):
        pool = ConnectionPool(make_conn, max_size=2, timeout=1)
        c = pool.acquire()
        assert c is not None
        pool.release(c)

    def test_release_makes_conn_reusable(self):
        pool = ConnectionPool(make_conn, max_size=2, timeout=1)
        c1 = pool.acquire()
        pool.release(c1)
        c2 = pool.acquire()
        assert c1 is c2, "released connection should be reused"
        pool.release(c2)

    def test_pool_size_never_exceeds_max(self):
        """Under concurrent load, pool must never exceed max_size connections."""
        max_size = 5
        pool = ConnectionPool(make_conn, max_size=max_size, timeout=2)
        created = []
        errors = []

        def worker():
            try:
                c = pool.acquire()
                time.sleep(0.02)
                pool.release(c)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"unexpected errors: {errors}"
        # _counter tells us how many connections were ever created
        assert _counter <= max_size, (
            f"pool created {_counter} connections but max_size={max_size}"
        )


# ── timeout / exhaustion ──────────────────────────────────────────────────────

class TestExhaustion:
    def test_raises_when_pool_exhausted(self):
        pool = ConnectionPool(make_conn, max_size=1, timeout=0.1)
        c = pool.acquire()
        with pytest.raises(PoolExhaustedError):
            pool.acquire()   # pool full, should time out
        pool.release(c)

    def test_acquire_succeeds_after_release_unblocks(self):
        pool = ConnectionPool(make_conn, max_size=1, timeout=2)
        c1 = pool.acquire()

        result = []
        def waiter():
            result.append(pool.acquire())

        t = threading.Thread(target=waiter)
        t.start()
        time.sleep(0.05)
        pool.release(c1)
        t.join(timeout=1)
        assert result, "waiter should have received a connection"
        pool.release(result[0])


# ── close semantics ───────────────────────────────────────────────────────────

class TestClose:
    def test_acquire_after_close_raises(self):
        pool = ConnectionPool(make_conn, max_size=2, timeout=1)
        pool.close()
        with pytest.raises(PoolClosedError):
            pool.acquire()

    def test_close_unblocks_waiting_acquirers(self):
        """A thread blocked in acquire() must wake up and raise PoolClosedError when
        pool.close() is called from another thread."""
        pool = ConnectionPool(make_conn, max_size=1, timeout=5)
        c = pool.acquire()

        errors = []
        def waiter():
            try:
                pool.acquire()
            except PoolClosedError as e:
                errors.append(e)

        t = threading.Thread(target=waiter)
        t.start()
        time.sleep(0.05)   # give waiter time to block
        pool.close()
        t.join(timeout=1)
        assert t.is_alive() is False, "waiter thread must unblock after close()"
        assert errors, "waiter must raise PoolClosedError"

    def test_close_closes_idle_connections(self):
        pool = ConnectionPool(make_conn, max_size=3, timeout=1)
        conns = [pool.acquire() for _ in range(3)]
        for c in conns:
            pool.release(c)
        idle_conns = list(pool._idle)
        pool.close()
        for c in idle_conns:
            assert c.closed, "idle connections should be closed on pool.close()"


# ── double-release guard ──────────────────────────────────────────────────────

class TestDoubleRelease:
    def test_double_release_raises(self):
        """Releasing a connection that is not in-use must raise ValueError."""
        pool = ConnectionPool(make_conn, max_size=2, timeout=1)
        c = pool.acquire()
        pool.release(c)
        with pytest.raises((ValueError, AssertionError)):
            pool.release(c)   # double-release

    def test_foreign_connection_release_raises(self):
        """Releasing an object not acquired from this pool must raise ValueError."""
        pool = ConnectionPool(make_conn, max_size=2, timeout=1)
        foreign = FakeConn(999)
        with pytest.raises((ValueError, AssertionError)):
            pool.release(foreign)
