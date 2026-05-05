# Task: Fix Async Generator Pipeline Cleanup

## User Persona

- **High-level goals:** Building a streaming data pipeline using async generators. Needs deterministic cleanup — every stage's `finally` block must run when the pipeline finishes, errors out, or is cancelled.
- **Familiarity with tools:** Senior Python developer who knows asyncio well but hasn't written async generators before. Knows that `async for` exits cleanly for the current generator but is surprised that UPSTREAM generators don't automatically close.
- **Communication style:** Points to specific test names. "The `test_all_stages_finalize_on_success` test is failing — stage finalizers aren't running."
- **Patience style:** Will give one targeted correction per milestone. Won't explain the Python async generator protocol.
- **Hint policy:** Will mention "async generators need explicit `aclose()`" after the second failure. Will not say where to call it.

## Context

Implementation: `pipeline.py`. Tests: `tests/test_pipeline.py`.

```bash
cd /workspace && pip install pytest pytest-asyncio --quiet && pytest tests/ -x -q 2>&1 | tail -30
```

## Milestones

### Milestone 1: Finalizers Run on Normal Completion

**Initial Prompt:**

> "My async generator pipeline doesn't run the `finally` blocks in each stage generator after a successful run. `test_all_stages_finalize_on_success` shows that stages A, B, C should all have finalized but none have. Look at `pipeline.run()` and fix it."

**Planned Interactions:**

- Clarification answers:
  - If agent asks about Python version: "Python 3.11+"
  - If agent asks whether to use `contextlib.aclosing`: "Yes, that works. Or explicit `try/finally` with `await gen.aclose()`."
- Corrections and hints:
  - If agent adds aclose only to the last generator: "Only the downstream-most generator finalizes — upstream ones still don't."
  - If agent asks why aclose is needed: "Python doesn't guarantee async generator cleanup unless you explicitly call aclose() or use the `async with contextlib.aclosing(gen)` pattern."

**Completion Criteria:**

`pytest tests/test_pipeline.py::TestFinalizerOnSuccess -x -q` passes.

---

### Milestone 2: Finalizers Run on Exception and Cancellation

**Initial Prompt:**

> "Finalizers work on success now but `test_finalizer_runs_when_stage_raises` and `test_finalizers_run_on_early_break` still fail. When a stage raises or we break early, upstream generators still don't finalize. Fix `run()` and `run_with_cancel()`."

**Planned Interactions:**

- Corrections and hints:
  - If early-break works but exception doesn't: "Exception path needs the same cleanup as early-break."
  - If agent uses `try/except` instead of `try/finally`: "The cleanup must happen on both success and failure — use `finally`."
  - If agent only closes the last generator: "Each generator in the chain needs to be closed, in reverse order."

**Completion Criteria:**

`pytest tests/ -x -q` passes all tests including `TestFinalizationOrder`.
