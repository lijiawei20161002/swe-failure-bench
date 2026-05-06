"""
Thread-safe connection pool with transaction support.

Connections are expensive to create (handshake, auth, etc.), so the pool
keeps a cache of idle connections and hands them out to callers.  Each
connection supports transactions: writes inside a transaction are invisible
to other connections until the transaction is committed; they are discarded
on rollback.

The pool must ensure that when a connection is returned and later reused,
the new user gets a connection in a clean, idle state — as if it were
freshly created.  Any open transaction from the previous user must be
rolled back before the connection re-enters the pool.

Public API:
    pool = ConnectionPool(max_size=5)
    with pool.acquire() as conn:
        conn.begin()
        conn.execute("INSERT", "key", "value")
        conn.commit()

    val = pool.direct_get("key")   # read committed data
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Any


class Connection:
    """
    Simulated database connection with transaction semantics.

    Writes inside a transaction are buffered until commit() or discarded
    on rollback().  Reads see the last committed state plus any writes
    made in the current transaction on this same connection.
    """

    def __init__(self, store: dict[str, Any]):
        # Shared committed store (all connections share the same dict)
        self._store = store
        self._txn_buffer: dict[str, Any] | None = None   # None = no active txn
        self.id = id(self)

    def begin(self) -> None:
        """Start a transaction."""
        if self._txn_buffer is not None:
            raise RuntimeError("Transaction already in progress")
        self._txn_buffer = {}

    def execute(self, key: str, value: Any) -> None:
        """Write a key-value pair (buffered if inside a transaction)."""
        if self._txn_buffer is not None:
            self._txn_buffer[key] = value
        else:
            self._store[key] = value

    def get(self, key: str) -> Any:
        """Read a value, seeing the current transaction's writes if any."""
        if self._txn_buffer is not None and key in self._txn_buffer:
            return self._txn_buffer[key]
        return self._store.get(key)

    def commit(self) -> None:
        """Commit the current transaction, making writes visible to all."""
        if self._txn_buffer is None:
            raise RuntimeError("No active transaction")
        self._store.update(self._txn_buffer)
        self._txn_buffer = None

    def rollback(self) -> None:
        """Discard the current transaction's writes."""
        self._txn_buffer = None

    @property
    def in_transaction(self) -> bool:
        return self._txn_buffer is not None


class ConnectionPool:
    """
    A fixed-size pool of reusable database connections.

    All connections share a single underlying in-memory store so that
    committed writes are immediately visible across connections.
    """

    def __init__(self, max_size: int = 5):
        self._store: dict[str, Any] = {}
        self._pool: list[Connection] = []
        self._lock = threading.Lock()
        self._max_size = max_size

    def _create_connection(self) -> Connection:
        return Connection(self._store)

    def _checkout(self) -> Connection:
        with self._lock:
            if self._pool:
                return self._pool.pop()
        return self._create_connection()

    def _checkin(self, conn: Connection) -> None:
        # Reset connection state before returning it to the pool so that
        # the next user gets a clean connection.
        if conn.in_transaction:
            conn.rollback()
        with self._lock:
            if len(self._pool) < self._max_size:
                self._pool.append(conn)

    @contextmanager
    def acquire(self):
        """Context manager that yields a connection and returns it on exit."""
        conn = self._checkout()
        try:
            yield conn
        finally:
            self._checkin(conn)

    def direct_get(self, key: str) -> Any:
        """Read a committed value directly from the shared store."""
        return self._store.get(key)

    def pool_size(self) -> int:
        """Number of idle connections currently in the pool."""
        with self._lock:
            return len(self._pool)
