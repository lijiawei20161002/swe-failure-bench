# Task: Fix Raft Log AppendEntries Handler

## User Persona

- **High-level goals:** Implementing the Raft consensus algorithm. The log's `append_entries` handler must be exactly correct — safety bugs here break distributed consistency.
- **Familiarity with tools:** Has read the Raft paper (Ongaro & Ousterhout §5.3). Knows the AppendEntries RPC contract. Will immediately spot "commit_index advanced on reject."
- **Communication style:** References the paper: "§5.3 says commit_index must only advance on successful AppendEntries, but your implementation advances it on rejection too."
- **Patience style:** Extremely precise. Will re-run the full test suite after each fix and report which tests still fail.
- **Hint policy:** Will quote the paper section number. Will not tell which line to change.

## Context

Implementation: `raft_log.py`. Tests: `tests/test_raft_log.py`.

```bash
cd /workspace && pip install pytest --quiet && pytest tests/ -x -q 2>&1 | tail -30
```

## Milestones

### Milestone 1: Fix Commit Index Advancing on Rejection

**Initial Prompt:**

> "The Raft log advances `commit_index` even when `append_entries` is rejected (consistency check fails). This violates the Raft spec: commit_index must only advance on SUCCESSFUL appends. See `test_reject_does_not_advance_commit_index`. Fix `append_entries` in `raft_log.py`."

**Planned Interactions:**

- Clarification answers:
  - If agent asks where the call is: "Look at the rejection path — when False is returned, `_maybe_update_commit` must not be called."
- Corrections and hints:
  - If agent moves the call but breaks success path: "On successful appends, commit_index still needs to advance."

**Completion Criteria:**

`pytest tests/test_raft_log.py::TestConsistencyCheck -x -q` passes.

---

### Milestone 2: Fix Truncation with prev_index=0

**Initial Prompt:**

> "There's still a bug in the conflict-handling path. When `prev_index=0` and the new entries list contains BOTH matching and conflicting entries, the conflicting entries are handled correctly but ALL new entries get appended instead of just the entries from the conflict point onward. `test_overwrite_from_prev_index_zero` catches this. Fix `append_entries`."

**Planned Interactions:**

- Clarification answers:
  - If agent asks about the algorithm: "After truncating at the conflict index, you should only append `entries[conflict_index - prev_index - 1:]` — the slice of new entries starting at the conflict point, not all of them."
  - If agent asks what conflict_index represents: "It's the 1-based log index of the first conflicting entry. The corresponding position in `entries` is `conflict_index - prev_index - 1`."
- Corrections and hints:
  - If agent changes the slice but the test still fails: "Check your arithmetic — if prev_index=0 and conflict is at log index 2, the entries slice start should be 2-0-1=1."

**Completion Criteria:**

`pytest tests/ -x -q` passes all tests.
