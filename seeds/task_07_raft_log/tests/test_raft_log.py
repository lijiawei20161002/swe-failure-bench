"""Tests for Raft log. Run: pytest tests/ -x"""
import pytest
from raft_log import RaftLog, LogEntry


def mk(*pairs) -> list[LogEntry]:
    """Build list of LogEntry from (index, term) pairs."""
    return [LogEntry(index=i, term=t) for i, t in pairs]


def append(log, prev_index, prev_term, entries, leader_commit=0):
    return log.append_entries(prev_index, prev_term, entries, leader_commit)


# ── basic ─────────────────────────────────────────────────────────────────────

class TestBasic:
    def test_initial_state(self):
        log = RaftLog()
        assert log.last_log_index == 0
        assert log.last_log_term == 0
        assert log.commit_index == 0

    def test_append_single_entry(self):
        log = RaftLog()
        ok = append(log, 0, 0, mk((1, 1)))
        assert ok is True
        assert log.last_log_index == 1
        assert log.get_entry(1).term == 1

    def test_append_multiple_entries(self):
        log = RaftLog()
        ok = append(log, 0, 0, mk((1, 1), (2, 1), (3, 1)))
        assert ok is True
        assert log.last_log_index == 3


# ── consistency check ─────────────────────────────────────────────────────────

class TestConsistencyCheck:
    def test_reject_when_prev_index_missing(self):
        log = RaftLog()
        ok = append(log, 5, 1, mk((6, 1)))
        assert ok is False, "Should reject: prev_index=5 not in log"

    def test_reject_when_prev_term_mismatch(self):
        log = RaftLog()
        append(log, 0, 0, mk((1, 1)))
        ok = append(log, 1, 2, mk((2, 2)))   # prev_term=2 but actual=1
        assert ok is False, "Should reject: term mismatch at prev_index=1"

    def test_accept_at_empty_log(self):
        log = RaftLog()
        ok = append(log, 0, 0, mk((1, 1)))
        assert ok is True

    def test_reject_does_not_advance_commit_index(self):
        """
        BUG B: when append_entries is rejected, the commit_index must NOT
        be advanced. Only successful appends may advance commit.
        """
        log = RaftLog()
        append(log, 0, 0, mk((1, 1)))
        assert log.commit_index == 0

        # This RPC is rejected (prev_term mismatch)
        ok = append(log, 1, 99, mk((2, 2)), leader_commit=5)
        assert ok is False
        assert log.commit_index == 0, (
            f"commit_index advanced to {log.commit_index} after rejected AppendEntries. "
            "BUG B: _maybe_update_commit() called even on rejection path."
        )


# ── truncation / overwrite (BUG C) ───────────────────────────────────────────

class TestTruncation:
    def test_overwrite_from_prev_index_zero(self):
        """
        BUG C: When prev_index=0 and the new entries list contains BOTH
        entries that match existing ones AND entries that conflict, only the
        conflicting entries and beyond should be replaced.

        Log: [(1,t1),(2,t1),(3,t1)]
        Call: append(log, 0, 0, [(1,t1),(2,t2),(3,t2)])
          entries[0]=(1,t1) matches existing → no conflict
          entries[1]=(2,t2) conflicts with existing (2,t1) → conflict_index=2

        Fix: append only entries[conflict_index - prev_index - 1:] = entries[1:]
        BUG C: appends all of entries → duplicates entry 1.
        Expected: [(1,t1),(2,t2),(3,t2)], last_index=3
        Buggy:    [(1,t1),(1,t1),(2,t2),(3,t2)], last_index=4
        """
        log = RaftLog()
        append(log, 0, 0, mk((1, 1), (2, 1), (3, 1)))

        ok = append(log, 0, 0, mk((1, 1), (2, 2), (3, 2)))
        assert ok is True
        assert log.last_log_index == 3, (
            f"Expected 3 entries after conflict-overwrite with prev_index=0, "
            f"got {log.last_log_index}. BUG C: entries duplicated when appending "
            "from wrong offset."
        )
        assert log.get_entry(1).term == 1   # first entry unchanged
        assert log.get_entry(2).term == 2   # conflict point overwritten
        assert log.get_entry(3).term == 2

    def test_conflicting_entry_gets_overwritten(self):
        """
        If a new entry at index i has a different term than existing entry i,
        the existing entry and all that follow must be deleted, replaced by
        the leader's entries.
        """
        log = RaftLog()
        append(log, 0, 0, mk((1, 1), (2, 1), (3, 1)))

        # Leader sends conflicting entry at index 2 (different term)
        ok = append(log, 1, 1, mk((2, 2), (3, 2)))
        assert ok is True
        assert log.last_log_index == 3
        assert log.get_entry(2).term == 2, (
            f"Entry 2 should have term 2 after overwrite, got {log.get_entry(2).term}"
        )
        assert log.get_entry(3).term == 2

    def test_truncation_does_not_duplicate_entries(self):
        """
        BUG C: When entries conflict, the fix should append only the entries
        starting from the conflict point — not ALL entries from the start.

        If log has [t1, t1, t1] at indices [1,2,3] and leader sends
        prev=(1,t1) with new_entries=[(2,t2),(3,t2)]:
          - Index 2 conflicts (t1 vs t2)
          - Truncate from index 2 → log becomes [(1,t1)]
          - Append (2,t2),(3,t2) → log becomes [(1,t1),(2,t2),(3,t2)]
          - Final length: 3 entries

        BUG C appends ALL of new_entries from index 0, causing duplication.
        """
        log = RaftLog()
        append(log, 0, 0, mk((1, 1), (2, 1), (3, 1)))

        ok = append(log, 1, 1, mk((2, 2), (3, 2)))
        assert ok is True
        assert log.last_log_index == 3, (
            f"Expected 3 entries after overwrite, got {log.last_log_index}. "
            "BUG C: entries may be duplicated if fix appends from wrong offset."
        )
        # Verify the log is exactly [(1,t1),(2,t2),(3,t2)]
        assert log.get_entry(1).term == 1
        assert log.get_entry(2).term == 2
        assert log.get_entry(3).term == 2

    def test_partial_conflict_only_truncates_from_conflict(self):
        """Only entries from the conflict point onward are removed."""
        log = RaftLog()
        append(log, 0, 0, mk((1, 1), (2, 1), (3, 1), (4, 1)))

        # Conflict at index 3 only
        ok = append(log, 2, 1, mk((3, 2), (4, 2), (5, 2)))
        assert ok is True
        assert log.get_entry(1).term == 1   # unchanged
        assert log.get_entry(2).term == 1   # unchanged
        assert log.get_entry(3).term == 2   # overwritten
        assert log.last_log_index == 5


# ── commit index ──────────────────────────────────────────────────────────────

class TestCommitIndex:
    def test_commit_advances_with_leader_commit(self):
        log = RaftLog()
        append(log, 0, 0, mk((1, 1), (2, 1), (3, 1)), leader_commit=2)
        assert log.commit_index == 2

    def test_commit_capped_at_last_log_index(self):
        """leader_commit may exceed our log length — cap at last_log_index."""
        log = RaftLog()
        append(log, 0, 0, mk((1, 1)), leader_commit=100)
        assert log.commit_index == 1

    def test_commit_does_not_go_backward(self):
        log = RaftLog()
        append(log, 0, 0, mk((1, 1), (2, 1)), leader_commit=2)
        append(log, 2, 1, mk((3, 1)), leader_commit=1)   # leader_commit < current
        assert log.commit_index == 2   # must not regress

    def test_manual_commit(self):
        log = RaftLog()
        append(log, 0, 0, mk((1, 1), (2, 1)))
        log.commit(2)
        assert log.commit_index == 2

    def test_commit_beyond_log_raises(self):
        log = RaftLog()
        append(log, 0, 0, mk((1, 1)))
        with pytest.raises(ValueError):
            log.commit(5)


# ── log matching property ─────────────────────────────────────────────────────

class TestLogMatchingProperty:
    def test_two_logs_match_up_to_common_index(self):
        """
        If two logs agree at (index, term), they must be identical up to that point.
        This property is critical for Raft safety.
        """
        log1 = RaftLog()
        log2 = RaftLog()

        # Both start with same entries through index 3
        append(log1, 0, 0, mk((1, 1), (2, 1), (3, 1)))
        append(log2, 0, 0, mk((1, 1), (2, 1), (3, 1)))

        # log1 gets extra entries
        append(log1, 3, 1, mk((4, 2), (5, 2)))

        # Both agree at index=3, term=1
        # Entries through index 3 must be identical
        for i in range(1, 4):
            assert log1.get_entry(i).term == log2.get_entry(i).term, (
                f"Logs differ at index {i} despite agreeing at (3, 1)"
            )

    def test_append_idempotent_for_matching_entries(self):
        """Re-sending already-present entries must not change the log."""
        log = RaftLog()
        append(log, 0, 0, mk((1, 1), (2, 1), (3, 1)))
        # Re-send same entries
        append(log, 0, 0, mk((1, 1), (2, 1), (3, 1)))
        assert log.last_log_index == 3
        for i in range(1, 4):
            assert log.get_entry(i).term == 1
