"""
Write-ahead log (WAL) with checkpoint-based crash recovery.

Every mutation is appended to the WAL before being applied to the
in-memory state.  Periodically a checkpoint is taken: the current state
is persisted to a snapshot and a CHECKPOINT record is written to the WAL
recording the log sequence number (LSN) of the last entry included in
the snapshot.

On recovery after a crash, the engine:
  1. Loads the latest snapshot (restoring state as of the checkpoint).
  2. Replays WAL entries that were NOT yet included in the snapshot.

The boundary condition:

  * The snapshot captures the state AFTER applying entry checkpoint_lsn.
  * Therefore recovery must replay entries with LSN STRICTLY GREATER
    THAN checkpoint_lsn  (i.e., LSN > checkpoint_lsn).
  * Replaying checkpoint_lsn itself would apply that operation a second
    time, corrupting the recovered state.

Public API:
    db = Database()
    db.set("k", "v")
    db.increment("counter")
    db.checkpoint()
    db.set("k", "v2")

    # simulate crash + recovery
    db2 = Database.recover(db._wal_log, db._snapshot)
    assert db2.get("k") == "v2"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── WAL record types ──────────────────────────────────────────────────────────

@dataclass
class SetRecord:
    lsn: int
    key: str
    value: Any

@dataclass
class IncrRecord:
    lsn: int
    key: str
    amount: int = 1

@dataclass
class CheckpointRecord:
    lsn: int           # LSN of this checkpoint record itself
    snapshot_lsn: int  # LSN of the last entry included in the snapshot


# ── Database ──────────────────────────────────────────────────────────────────

class Database:
    """
    Simple key-value store backed by a WAL with checkpoint/recovery.
    """

    def __init__(self):
        self._state: dict[str, Any] = {}
        self._lsn: int = 0
        self._wal_log: list = []            # all WAL records in order
        self._snapshot: dict | None = None  # latest snapshot state
        self._checkpoint_lsn: int = -1      # last snapshot_lsn (-1 = none)

    # ── mutations ──────────────────────────────────────────────────────────────

    def _next_lsn(self) -> int:
        self._lsn += 1
        return self._lsn

    def set(self, key: str, value: Any) -> None:
        lsn = self._next_lsn()
        self._wal_log.append(SetRecord(lsn, key, value))
        self._state[key] = value

    def increment(self, key: str, amount: int = 1) -> None:
        lsn = self._next_lsn()
        self._wal_log.append(IncrRecord(lsn, key, amount))
        self._state[key] = self._state.get(key, 0) + amount

    # ── checkpoint ─────────────────────────────────────────────────────────────

    def checkpoint(self) -> None:
        """
        Persist the current state as a snapshot and record the checkpoint
        in the WAL.  The snapshot_lsn is the highest LSN whose effect is
        captured in the snapshot.
        """
        snapshot_lsn = self._lsn          # all entries up to here are in snapshot
        self._snapshot = dict(self._state) # capture current state
        self._checkpoint_lsn = snapshot_lsn

        ckpt_lsn = self._next_lsn()
        self._wal_log.append(CheckpointRecord(lsn=ckpt_lsn, snapshot_lsn=snapshot_lsn))

    # ── reads ──────────────────────────────────────────────────────────────────

    def get(self, key: str) -> Any:
        return self._state.get(key)

    # ── recovery ───────────────────────────────────────────────────────────────

    @classmethod
    def recover(cls, wal_log: list, snapshot: dict | None) -> "Database":
        """
        Reconstruct database state from a snapshot + WAL replay.

        Finds the latest CheckpointRecord in the WAL to determine which
        entries are already captured by the snapshot, then replays only
        the entries that follow.
        """
        db = cls()

        # Find the most recent checkpoint
        checkpoint_rec = None
        for record in reversed(wal_log):
            if isinstance(record, CheckpointRecord):
                checkpoint_rec = record
                break

        if checkpoint_rec is not None and snapshot is not None:
            # Restore from snapshot
            db._state = dict(snapshot)
            replay_from_lsn = checkpoint_rec.snapshot_lsn
        else:
            # No checkpoint — replay everything from the beginning
            replay_from_lsn = -1

        for record in wal_log:
            if isinstance(record, (SetRecord, IncrRecord)):
                if record.lsn > replay_from_lsn:
                    cls._apply(db, record)

        return db

    @staticmethod
    def _apply(db: "Database", record) -> None:
        """Apply a single WAL record to the database state."""
        if isinstance(record, SetRecord):
            db._state[record.key] = record.value
        elif isinstance(record, IncrRecord):
            db._state[record.key] = db._state.get(record.key, 0) + record.amount
