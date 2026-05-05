# Task: Fix Reference-Counted GC with Cycle Detection

## User Persona

- **High-level goals:** Building a custom memory manager with Python-style cycle detection. Needs the tricolor mark-and-sweep to correctly identify cyclic garbage while not touching externally-referenced objects.
- **Familiarity with tools:** Has read CPython's `gcmodule.c`. Knows the "subtract internal references" step is the key to the algorithm. Will spot "you're decrementing the holder's gc_refs instead of the target's gc_refs."
- **Communication style:** Very precise. "The `test_asymmetric_refs_cycle_collected` test fails — your algorithm collects `root` even though it has an external reference. The gc_refs subtraction is inverted."
- **Patience style:** Will pinpoint the exact wrong line if given two attempts.
- **Hint policy:** Will quote CPython GC algorithm step 2 if asked.

## Context

Implementation: `ref_graph.py`. Tests: `tests/test_gc.py`.

```bash
cd /workspace && pip install pytest --quiet && pytest tests/ -x -q 2>&1 | tail -30
```

## Milestones

### Milestone 1: Fix gc_refs Subtraction Direction

**Initial Prompt:**

> "The cycle detector is collecting externally-referenced objects it shouldn't. `test_asymmetric_refs_cycle_collected` and `test_mixed_reachable_and_cycle` both fail. The problem is in step 2 of `collect()`: when object A holds a reference to object B, you should subtract 1 from B's gc_refs (because A accounts for one of B's references). But the code subtracts from A's gc_refs instead. Fix the subtraction direction."

**Planned Interactions:**

- Clarification answers:
  - If agent asks why: "The goal is: after step 2, gc_refs[x] > 0 means x has references from outside the candidate set (external refs). We simulate 'removing' all internal references. For each ref A→B, we subtract 1 from B's count (B has one fewer internal referrer)."
  - If agent asks which variable: "In the inner loop `for ref in o.refs:`, you should be modifying `gc_refs[id(ref)]`, not `gc_refs[id(o)]`."
- Corrections and hints:
  - If agent fixes the direction but worklist is still wrong: "After fixing the subtraction, verify the worklist correctly identifies objects with gc_refs > 0 as the seeds for reachability."

**Completion Criteria:**

`pytest tests/test_gc.py::TestCycleDetection tests/test_gc.py::TestRefCounting -x -q` passes.

---

### Milestone 2: Fix Finalizer Object Cleanup

**Initial Prompt:**

> "Cycle detection is correct now. Last bug: `test_finalizer_object_refs_cleared` fails. When a finalizer object goes into `_garbage`, its outgoing references are never cleared, so the objects IT points to are kept alive forever (memory leak). After putting the finalizer object in garbage, clear its refs list and decrement the refcounts of everything it pointed to."

**Planned Interactions:**

- Clarification answers:
  - If agent asks why this matters: "The finalizer object itself can't be freed (it has __del__), but everything IT references should be freed if there are no other refs to them. Clearing the finalizer object's refs allows those referents to be collected."
- Corrections and hints:
  - If agent calls `_decref` on each ref and gets errors: "Be careful about the refcount going to 0 during iteration — iterate over a copy of the refs list first."

**Completion Criteria:**

`pytest tests/ -x -q` passes all tests.
