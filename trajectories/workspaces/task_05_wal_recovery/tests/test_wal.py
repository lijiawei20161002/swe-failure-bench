"""
Tests for WAL-based crash recovery.
Run: pip install pytest && pytest tests/ -x -q
"""
import pytest
from wal import Database


class TestBasicOperations:
    def test_set_get(self):
        db = Database()
        db.set("k", "v")
        assert db.get("k") == "v"

    def test_missing_key(self):
        assert Database().get("nope") is None

    def test_overwrite(self):
        db = Database()
        db.set("k", "a")
        db.set("k", "b")
        assert db.get("k") == "b"

    def test_increment(self):
        db = Database()
        db.increment("counter")
        db.increment("counter")
        db.increment("counter")
        assert db.get("counter") == 3

    def test_increment_by_amount(self):
        db = Database()
        db.increment("n", 5)
        db.increment("n", 3)
        assert db.get("n") == 8

    def test_set_then_increment(self):
        db = Database()
        db.set("n", 10)
        db.increment("n", 5)
        assert db.get("n") == 15


class TestRecoveryNoCheckpoint:
    """Recovery without a checkpoint replays the full WAL."""

    def test_recover_set(self):
        db = Database()
        db.set("k", "v")
        db2 = Database.recover(db._wal_log, None)
        assert db2.get("k") == "v"

    def test_recover_increment(self):
        db = Database()
        db.increment("n", 3)
        db.increment("n", 7)
        db2 = Database.recover(db._wal_log, None)
        assert db2.get("n") == 10

    def test_recover_empty_log(self):
        db = Database()
        db2 = Database.recover(db._wal_log, None)
        assert db2.get("k") is None


class TestRecoveryWithCheckpoint:
    """
    The critical tests: recovery after a checkpoint must replay only the
    entries that were NOT yet included in the snapshot.

    The checkpoint records snapshot_lsn = the LSN of the last entry
    already applied in the snapshot.  Entries with LSN <= snapshot_lsn
    are captured by the snapshot and must NOT be replayed.  Only entries
    with LSN > snapshot_lsn require replay.

    BUG: the recover() method uses `>=` instead of `>`, so the entry AT
    snapshot_lsn is replayed a second time, doubling its effect.
    """

    def test_checkpoint_then_recover_no_new_ops(self):
        """No operations after checkpoint → recovered state matches original."""
        db = Database()
        db.set("k", "v")
        db.increment("n", 5)
        db.checkpoint()

        db2 = Database.recover(db._wal_log, db._snapshot)
        assert db2.get("k") == "v"
        assert db2.get("n") == 5

    def test_checkpoint_then_new_ops_recovered(self):
        """Operations after the checkpoint must be replayed."""
        db = Database()
        db.set("k", "before")
        db.checkpoint()
        db.set("k", "after")

        db2 = Database.recover(db._wal_log, db._snapshot)
        assert db2.get("k") == "after"

    def test_increment_not_doubled_after_checkpoint(self):
        """
        Core correctness: the last entry before a checkpoint must not be
        replayed again during recovery.

        Sequence:
          increment("counter", 1)  → counter = 1, LSN = 1
          checkpoint()              → snapshot captures counter=1, snapshot_lsn=1
          increment("counter", 1)  → counter = 2, LSN = 2 (post-checkpoint)

        Recovery should:
          1. Load snapshot → counter = 1
          2. Replay LSN > 1 → replay LSN=2 → counter = 2

        With the bug (>= instead of >):
          1. Load snapshot → counter = 1
          2. Replay LSN >= 1 → replay LSN=1 AND LSN=2 → counter = 1+1+1 = 3
        """
        db = Database()
        db.increment("counter")   # LSN 1 → counter = 1
        db.checkpoint()           # snapshot_lsn = 1, snapshot = {counter: 1}
        db.increment("counter")   # LSN 3 → counter = 2

        db2 = Database.recover(db._wal_log, db._snapshot)
        assert db2.get("counter") == 2, (
            f"Expected counter=2 after recovery, got {db2.get('counter')}. "
            "The increment at snapshot_lsn was replayed again during recovery. "
            "WAL replay must start at LSN > snapshot_lsn (strictly greater), "
            "not LSN >= snapshot_lsn."
        )

    def test_set_not_doubled_after_checkpoint(self):
        """A set() at the checkpoint boundary must not be reapplied."""
        db = Database()
        db.set("mode", "read-write")  # LSN 1
        db.checkpoint()               # snapshot_lsn = 1
        # No further operations

        db2 = Database.recover(db._wal_log, db._snapshot)
        # set is idempotent so doubling doesn't change the value,
        # but we verify the state is correct
        assert db2.get("mode") == "read-write"

    def test_multiple_ops_before_checkpoint(self):
        """All pre-checkpoint operations are captured in snapshot, none replayed."""
        db = Database()
        for i in range(5):
            db.increment("total", i)   # total = 0+1+2+3+4 = 10
        db.checkpoint()

        db2 = Database.recover(db._wal_log, db._snapshot)
        assert db2.get("total") == 10, (
            f"Expected total=10, got {db2.get('total')}. "
            "Pre-checkpoint increments are being replayed despite being "
            "captured in the snapshot."
        )

    def test_post_checkpoint_ops_only_replayed_once(self):
        """Operations after the checkpoint are replayed exactly once."""
        db = Database()
        db.increment("a", 10)
        db.checkpoint()
        db.increment("a", 5)   # only this should be replayed

        db2 = Database.recover(db._wal_log, db._snapshot)
        assert db2.get("a") == 15, (
            f"Expected a=15, got {db2.get('a')}. "
            "Either pre-checkpoint op was replayed (a=25) or "
            "post-checkpoint op was missed (a=10)."
        )

    def test_recovery_idempotent(self):
        """Recovering twice from the same log produces the same result."""
        db = Database()
        db.set("x", 1)
        db.checkpoint()
        db.set("x", 2)

        db2 = Database.recover(db._wal_log, db._snapshot)
        db3 = Database.recover(db._wal_log, db._snapshot)
        assert db2.get("x") == db3.get("x") == 2

    def test_checkpoint_mid_sequence(self):
        """Checkpoint in the middle of a longer sequence."""
        db = Database()
        db.increment("n")        # 1
        db.increment("n")        # 2
        db.checkpoint()          # snapshot: n=2
        db.increment("n")        # 3
        db.increment("n")        # 4

        db2 = Database.recover(db._wal_log, db._snapshot)
        assert db2.get("n") == 4
