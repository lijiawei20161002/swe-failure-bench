# Task: Fix Rope Data Structure

## User Persona

- **High-level goals:** Using a rope for a text editor. Needs correct split and concat that preserve every character.
- **Familiarity with tools:** Has read the Boehm-Atkinson-Plass rope paper. Knows that `split(i)` should produce left with chars `[0, i)` and right with chars `[i, end)` — the character AT index `i` goes to the RIGHT side.
- **Communication style:** Tests with specific strings and split points: "Rope('hello').split(2) should give ('he', 'llo') not ('he', 'lo') — the 'l' at index 2 is missing."
- **Patience style:** Rigorous. Runs the full test suite. Expects round-trips to hold.
- **Hint policy:** Will state the invariant: "No character should be lost. split + concat is identity."

## Context

Implementation: `rope.py`. Tests: `tests/test_rope.py`.

```bash
cd /workspace && pip install pytest --quiet && pytest tests/ -x -q 2>&1 | tail -30
```

## Milestones

### Milestone 1: Fix Character Loss in Leaf Split

**Initial Prompt:**

> "Characters are being lost when splitting. `Rope('hello').split(2)` gives `('he', 'lo')` — the 'l' at index 2 is dropped. The left side should be `'he'` and the right side should be `'llo'`. Fix `rope.py`."

**Planned Interactions:**

- Clarification answers:
  - If agent asks about the split semantics: "split(i) → (first i chars, remaining chars). Characters [0,i) go left; character at i and everything after goes right."
  - If agent asks which function: "Look at the `_split` function — specifically the leaf case."
- Corrections and hints:
  - If agent fixes the leaf but longer strings still fail: "Run `test_split_long_string` — splits of strings longer than `_MAX_LEAF` still lose characters."

**Completion Criteria:**

`pytest tests/test_rope.py::TestSplit -x -q` passes.

---

### Milestone 2: Fix Boundary Split in Internal Nodes

**Initial Prompt:**

> "The simple splits work now but `test_split_preserves_all_characters` still fails for some split points. Specifically, splitting at the boundary between left and right subtrees (where i == the left subtree's length) produces a wrong result. Fix it."

**Planned Interactions:**

- Clarification answers:
  - If agent asks what "boundary" means: "For an internal node with weight=W (left subtree length), splitting at exactly i=W should just return (left_subtree, right_subtree) — no further recursion needed."
- Corrections and hints:
  - If agent fixes boundary but other internal splits break: "Make sure the general cases (i < weight and i > weight) still work."

**Completion Criteria:**

`pytest tests/ -x -q` passes all tests including `TestRoundTrip` and `TestSlice`.
