"""
Tests for ConnectionPool.
Run: pip install pytest && pytest tests/ -x -q
"""
import pytest
from connpool import ConnectionPool


class TestBasicPool:
    def test_acquire_and_release(self):
        pool = ConnectionPool()
        with pool.acquire() as conn:
            assert conn is not None

    def test_connection_reuse(self):
        pool = ConnectionPool()
        with pool.acquire() as c1:
            id1 = c1.id
        with pool.acquire() as c2:
            id2 = c2.id
        assert id1 == id2   # same connection object reused

    def test_pool_size_after_release(self):
        pool = ConnectionPool()
        with pool.acquire():
            assert pool.pool_size() == 0
        assert pool.pool_size() == 1

    def test_committed_write_visible(self):
        pool = ConnectionPool()
        with pool.acquire() as conn:
            conn.begin()
            conn.execute("k", "v")
            conn.commit()
        assert pool.direct_get("k") == "v"

    def test_uncommitted_write_not_visible(self):
        pool = ConnectionPool()
        with pool.acquire() as conn:
            conn.begin()
            conn.execute("secret", "hidden")
            # no commit
        # The pool._store should NOT have "secret" because txn wasn't committed
        assert pool.direct_get("secret") is None

    def test_rollback_discards_writes(self):
        pool = ConnectionPool()
        with pool.acquire() as conn:
            conn.begin()
            conn.execute("k", "v")
            conn.rollback()
        assert pool.direct_get("k") is None

    def test_autocommit_write(self):
        """Writes outside a transaction are immediately committed."""
        pool = ConnectionPool()
        with pool.acquire() as conn:
            conn.execute("k", "v")
        assert pool.direct_get("k") == "v"


class TestTransactionIsolation:
    """
    Core correctness: when a connection is returned to the pool without
    committing or rolling back an open transaction, the next user must
    receive a connection in a clean, idle state.

    The bug: _checkin() returns the connection without calling rollback().
    The next user inherits the previous user's open transaction buffer,
    which means:
      - They see the previous user's uncommitted writes via conn.get().
      - If they call commit(), BOTH their writes AND the previous
        user's leaked writes are committed to the shared store.

    Fix: call conn.rollback() inside _checkin() before returning the
    connection to the pool.
    """

    def test_abandoned_transaction_not_visible_to_next_user(self):
        """
        User A starts a transaction and writes "ghost"="haunted", then
        releases the connection WITHOUT committing.  User B acquires the
        same connection and must NOT see "ghost" in the store.
        """
        pool = ConnectionPool()

        # User A: start transaction, write, do NOT commit, release
        with pool.acquire() as conn:
            conn.begin()
            conn.execute("ghost", "haunted")
            # deliberate: no commit, no rollback

        # User B: get a clean connection
        with pool.acquire() as conn:
            visible_to_b = conn.get("ghost")

        committed = pool.direct_get("ghost")

        assert visible_to_b is None, (
            f"User B's connection sees 'ghost'={visible_to_b!r} from "
            "User A's uncommitted transaction. The connection was returned "
            "to the pool without rolling back the open transaction. "
            "Fix: call conn.rollback() in _checkin() before pooling."
        )
        assert committed is None, (
            "The uncommitted write leaked into the committed store."
        )

    def test_leaked_transaction_not_committed_by_next_user(self):
        """
        If User A's leaked transaction merges with User B's commit, then
        User A's data appears in the store even though A never committed.
        """
        pool = ConnectionPool()

        # User A: open transaction with write "a"="leaked", release without commit
        with pool.acquire() as conn:
            conn.begin()
            conn.execute("a", "leaked")

        # User B: gets the same connection (still in A's transaction), writes "b"="ok"
        with pool.acquire() as conn:
            if not conn.in_transaction:
                conn.begin()
            conn.execute("b", "ok")
            conn.commit()   # should only commit b="ok", not a="leaked"

        assert pool.direct_get("b") == "ok"
        assert pool.direct_get("a") is None, (
            f"'a'={pool.direct_get('a')!r} was committed even though User A "
            "never called commit(). User A's leaked transaction buffer was "
            "inherited by User B and committed along with B's own writes."
        )

    def test_fresh_connection_has_no_transaction(self):
        """A freshly-acquired connection must not be in a transaction."""
        pool = ConnectionPool()

        # First user: open but don't close a transaction
        with pool.acquire() as conn:
            conn.begin()
            conn.execute("x", "1")
            # no commit

        # Second user: must get a clean connection
        with pool.acquire() as conn:
            assert not conn.in_transaction, (
                "Connection returned from pool is still in a transaction "
                "from the previous user. _checkin() must rollback before "
                "returning the connection to the pool."
            )

    def test_sequential_transactions_independent(self):
        """Two back-to-back transactions on the same connection are independent."""
        pool = ConnectionPool()

        with pool.acquire() as conn:
            conn.begin()
            conn.execute("k", "txn1")
            conn.commit()

        with pool.acquire() as conn:
            # Should start fresh, not see any lingering state
            assert not conn.in_transaction
            conn.begin()
            conn.execute("k", "txn2")
            conn.commit()

        assert pool.direct_get("k") == "txn2"

    def test_exception_during_transaction_does_not_leak(self):
        """
        If a caller raises an exception while a transaction is open, the
        connection is still returned to the pool via the finally block.
        The next user must not see the abandoned transaction.
        """
        pool = ConnectionPool()

        try:
            with pool.acquire() as conn:
                conn.begin()
                conn.execute("danger", "boom")
                raise RuntimeError("something went wrong")
        except RuntimeError:
            pass

        with pool.acquire() as conn:
            assert not conn.in_transaction
            assert conn.get("danger") is None, (
                "Previous user's uncommitted write is visible after exception."
            )

    def test_multiple_sequential_users_all_clean(self):
        """All successive users get a clean connection."""
        pool = ConnectionPool()

        for i in range(5):
            with pool.acquire() as conn:
                if i % 2 == 0:
                    conn.begin()
                    conn.execute(f"key{i}", f"val{i}")
                    # intentionally no commit on even iterations

        # All uncommitted writes must not have leaked
        for i in range(0, 5, 2):
            assert pool.direct_get(f"key{i}") is None, (
                f"key{i} leaked from an uncommitted transaction."
            )
