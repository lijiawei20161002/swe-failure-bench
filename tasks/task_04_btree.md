# Task: Fix B-Tree Split and Live Cursor

## User Persona

- **High-level goals:** Using a B-tree as the storage engine for a database index. Needs correct splits and a cursor that reflects live modifications.
- **Familiarity with tools:** Strong algorithms background. Has read CLRS. Knows the split algorithm cold — immediately spots "off by one in the median index."
- **Communication style:** Very precise: "After inserting [3,1,4,1,5,9,2,6], I see duplicate keys in the tree. The split is promoting the wrong median."
- **Patience style:** One correction per bug. Will immediately re-run the full test suite after each fix.
- **Hint policy:** Will quote CLRS §18.2 if the split fix is wrong. Will not give implementation hints for the cursor.

## Context

Implementation: `btree.py`. Tests: `tests/test_btree.py`.

```bash
cd /workspace && pip install pytest --quiet && pytest tests/ -x -q 2>&1 | tail -30
```

## Milestones

### Milestone 1: Fix the Split Algorithm

**Initial Prompt:**

> "The B-tree is creating duplicate keys after splits. Run the tests — `test_split_does_not_duplicate_keys` fails. The problem is in `_split_child`. For a node with 2t-1 keys, the median is at index t-1 (0-indexed), not t. Fix the split."

**Planned Interactions:**

- Clarification answers:
  - If agent asks about the split invariant: "Left child gets keys[:t-1], median gets promoted, right child gets keys[t:]."
  - If agent asks about children split: "Children split at t: left gets children[:t], right gets children[t:]."
- Corrections and hints:
  - If agent changes only some indices: "Check all three: y.keys split point, z.keys assignment, and y.children split point."

**Completion Criteria:**

`pytest tests/test_btree.py::TestSplitInvariant tests/test_btree.py::TestDelete -x -q` passes.

---

### Milestone 2: Fix the Live Cursor

**Initial Prompt:**

> "The cursor is broken — it snapshots keys at creation time, so deletions after `cursor()` isn't reflected. `test_cursor_reflects_deletions_after_creation` shows it returns a deleted key. The cursor must follow the live tree structure, not a snapshot."

**Planned Interactions:**

- Clarification answers:
  - If agent asks about the semantics: "Keys deleted after cursor creation must be skipped. Keys inserted in the not-yet-visited range must appear."
  - If agent asks about thread safety: "Single-threaded use only."
- Corrections and hints:
  - If agent regenerates a full list at each `next()`: "That's O(n) per call — use a position-tracking cursor (stack of node+index pairs)."
  - If agent fixes deletions but not insertions: "`test_cursor_includes_future_insertions_in_remaining_range` still fails."

**Completion Criteria:**

`pytest tests/ -x -q` passes all tests.
