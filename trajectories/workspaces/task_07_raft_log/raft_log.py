"""
Raft consensus log — the persistent log component of the Raft algorithm.

The log stores entries of the form (term, command). It enforces the
Raft log invariants required for safety:

  Log Matching Property:
    If two entries in different logs have the same index and term,
    then the logs are identical in all entries up through that index.

  Leader Completeness:
    If a log entry is committed in a given term, it will be present in
    the logs of all leaders for all higher-numbered terms.

This module implements the RaftLog class used by a Raft node for:
  - append_entries(prev_index, prev_term, entries, leader_commit):
      The core RPC handler from the leader. Must enforce log consistency.
  - commit(index): advance the commit index
  - get_entry(index): retrieve an entry by 1-based index
  - last_log_index / last_log_term: properties for vote requests

Based on: Ongaro & Ousterhout §5.3 "Log replication"
Used in: etcd, TiKV, CockroachDB.

All log indices are 1-based (Raft convention). Index 0 is a sentinel
(term=0, command=None) to simplify boundary cases.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class LogEntry:
    index: int
    term: int
    command: Any = None


class InconsistencyError(Exception):
    """Raised when an AppendEntries RPC fails the consistency check."""


class RaftLog:
    def __init__(self):
        # Sentinel at index 0 (term=0)
        self._entries: list[LogEntry] = [LogEntry(index=0, term=0)]
        self._commit_index: int = 0

    # ── properties ────────────────────────────────────────────────────────────

    @property
    def last_log_index(self) -> int:
        return len(self._entries) - 1

    @property
    def last_log_term(self) -> int:
        return self._entries[-1].term

    @property
    def commit_index(self) -> int:
        return self._commit_index

    # ── entry access ──────────────────────────────────────────────────────────

    def get_entry(self, index: int) -> Optional[LogEntry]:
        if 0 <= index < len(self._entries):
            return self._entries[index]
        return None

    def entries_from(self, start_index: int) -> list[LogEntry]:
        return list(self._entries[start_index:])

    # ── AppendEntries RPC handler ─────────────────────────────────────────────

    def append_entries(
        self,
        prev_index: int,
        prev_term: int,
        entries: list[LogEntry],
        leader_commit: int,
    ) -> bool:
        """
        Handle an AppendEntries RPC from the leader.

        Returns True if accepted, False if rejected (consistency check failed).

        Raft §5.3 algorithm:
        1. Reject if prev_index > last_log_index (we don't have that entry)
        2. Reject if log[prev_index].term != prev_term (term mismatch)
        3. For each new entry, if it conflicts with an existing entry (same
           index, different term), DELETE the conflicting entry and all
           that follow it.
        4. Append any new entries not already in the log.
        5. Update commit_index = min(leader_commit, last_log_index).
        """
        # Step 1: Consistency check — do we have the prev entry?
        if prev_index > self.last_log_index:
            return False

        # Step 2: Term check
        if self._entries[prev_index].term != prev_term:
            return False

        # Step 3 & 4: Process new entries
        conflict_index = None
        for i, entry in enumerate(entries):
            idx = prev_index + 1 + i
            if idx <= self.last_log_index:
                if self._entries[idx].term != entry.term:
                    conflict_index = idx
                    break
            # idx > last_log_index → just append

        if conflict_index is not None:
            # Truncate from conflict point
            self._entries = self._entries[:conflict_index]
            self._entries.extend(entries[conflict_index - prev_index - 1:])
        else:
            # No conflict — append only the truly new entries
            new_start = max(0, self.last_log_index - prev_index)
            self._entries.extend(entries[new_start:])

        # Step 5: Advance commit_index
        self._maybe_update_commit(leader_commit)
        return True

    def _maybe_update_commit(self, leader_commit: int) -> None:
        if leader_commit > self._commit_index:
            self._commit_index = min(leader_commit, self.last_log_index)

    # ── commit ────────────────────────────────────────────────────────────────

    def commit(self, index: int) -> None:
        """Advance commit index to *index* (must be <= last_log_index)."""
        if index > self.last_log_index:
            raise ValueError(f"Cannot commit {index} > {self.last_log_index}")
        self._commit_index = max(self._commit_index, index)

    # ── helpers ───────────────────────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self._entries) - 1   # exclude sentinel

    def __repr__(self) -> str:
        entries = self._entries[1:]
        return f"RaftLog(commit={self._commit_index}, entries={entries})"
