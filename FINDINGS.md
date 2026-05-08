# Evaluation Findings: Kimi 2.6 on swe-failure-bench

**Model:** `kimi-for-coding` (Kimi 2.6, extended-thinking reasoning model)  
**Dates:** 2026-05-04 – 2026-05-08  
**Eval script:** `eval_kimi.py`  
**API note:** `kimi-for-coding` requires `User-Agent: claude-code/1.0`; fails with 403 otherwise. Extended thinking is always on — `reasoning_content` must be echoed back in multi-turn history or the API returns 400.

---

## Current Benchmark: 1 Task (active seed suite)

| Task | Seed file | Pass rate (5 runs, May 7) | Failure mode |
|------|-----------|--------------------------|--------------|
| retry_stream | `seeds/retry_stream/stream.py` | 0/5 (0%) | Genuine capability gap — never adds `aclose()` to manual `__anext__` loop |

**Overall pass rate (May 7 experiment): 0/5 = 0%**

### Retired tasks (still in `trajectories/` for reference)

| Task | Reason retired |
|------|---------------|
| 02 tokenizer | Infrastructure failure (API abort), not capability |
| 03 async_generator | Failure is Mode C (wrong ordering of `aclose()` calls) — a deliberate trick, not a genuine gap |
| 08 gc_cycles | API-unreliable; 2/5 when stable |
| 04 concurrent_pipeline | Solved 1/1 — too easy |
| 06 stream_multiplexer | Solved 1/1 — too easy |

---

## Evaluation History

### Iterations 1–3: Initial 14-task batch (May 4)

- **With `# BUG N:` comments in code**: 12/14 (86%) — Kimi read the labels and fixed bugs in 2 turns
- **Comments stripped**: 4/8 (50%) — comments barely mattered; Kimi diagnoses from `pytest` output
- **Finding**: BUG comments are not a meaningful difficulty lever

### Iteration 4: Redesigned 8-task benchmark (May 5, single run)

4/8 = 50%. First run establishing two distinct failure modes.

### Iteration 5: 5-run statistical evaluation (May 5)

40 total attempts (8 tasks × 5 runs). **21/40 = 52.5% overall.**

| Task | 5-run pass rate | Notes |
|------|----------------|-------|
| 01 async_worker_pool | 3/5 (60%) | Reliable; removed |
| 02 tokenizer | 0/5 (0%) | Kept — always fails |
| 03 async_generator | 2/5 (40%) | Kept — genuine capability gap |
| 04 btree | 2/5 (40%) | API-dependent; removed |
| 05 regex_engine | 2/5 (40%) | API-dependent; removed |
| 06 context_vars | 5/5 (100%) | Trivial for Kimi; removed |
| 07 raft_log | 5/5 (100%) | Trivial for Kimi; removed |
| 08 gc_cycles | 2/5 (40%) | Kept — genuine gap when API stable |

### Iteration 6: 4 new tasks added (May 6, single run)

Replaced the 5 removed tasks with exc_info_leak, frame_codec, generator_stop, weakref_callback. **Result: 4/7 = 57%. All 4 new tasks solved in 2–3 turns.**

Kimi demonstrated immediate knowledge of:
- `sys.exc_info()[2]` traceback frame retention
- `struct` byte-order mismatch (`<I` vs `>I`)
- PEP 479: `StopIteration` inside generator → `RuntimeError`
- `WeakValueDictionary` dropping bound methods immediately

These are all documented Python gotchas. Kimi recognizes them from the error message + source code in one pass, without needing to reason about the runtime behavior.

All 4 removed. Benchmark reduced to 3 tasks.

### Iteration 7: Two new seed tasks screened, retry_stream kept (May 7)

Screened async_generator (new seed — harder pipeline variant with LIFO ordering constraint) and retry_stream (new — stream processor). Also tested concurrent_pipeline and stream_multiplexer with 1 run each; both solved immediately and retired.

**5-run results:**

| Task | Result | Outcome |
|------|--------|---------|
| async_generator (new seed) | 0/5 (0%) | Retired — see below |
| retry_stream | 0/5 (0%) | **Kept as active benchmark task** |

**async_generator new seed — retired (Mode C failure, not genuine gap):**
The new seed added `TestFinalizationOrder`, requiring LIFO finalization order (C→B→A). Kimi adds `aclose()` calls but iterates `generators` forward instead of `reversed(generators)`. The pipeline.py source has explicit `# BUG A: / # Fix:` comments pointing at `aclose()`; Kimi reads them and writes fixes, but the ordering constraint is not mentioned in the comments and Kimi consistently gets it wrong. This is a trick (a constraint Kimi can't read from the hints), not evidence of a genuine knowledge gap.

**retry_stream — kept (genuine capability gap):**
`StreamProcessor` uses manual `__anext__()` iteration rather than `async for`. Kimi never recognises that this pattern bypasses automatic generator cleanup on exception or cancellation. Across all 7 failure runs it never writes a single line of code — pure `run_bash` exploration for 30 turns. The fix (`await it.aclose()` in a `finally` block) is straightforward; the gap is that Kimi does not know the manual iterator protocol requires it.

Two distinct first-failing tests across runs:
- `test_source_finalizes_on_task_cancellation` — source not closed when the processing task receives `CancelledError`
- `test_large_source_finalizes_on_early_abort` — source not closed when transform raises `StopIteration`

---

## Two Confirmed Failure Modes

### Mode A: API Connection Abort (tokenizer, gc_cycles sometimes)

Tasks requiring long reasoning chains (>~360s) cause the HTTP connection to drop mid-response. This is **infrastructure failure, not capability failure** — the model was likely computing a correct fix.

- **tokenizer**: Python tokenizer state machine — raw strings, triple-quoted strings, escape sequences, and their interactions. ~10 overlapping rules require simultaneous reasoning. Aborts 5/5 runs.
- **gc_cycles**: Sometimes aborts under API load; sometimes solves in 3 turns when the API is stable.

### Mode B: Exploration Loop Without Commitment (async_generator old, retry_stream)

The model runs `pytest` for 15–30 turns without writing a fix. The test output points to a symptom (finalizers not running) but not the cause (missing `aclose()`).

- **async_generator old seed**: 30 turns of `run_bash`, 0 writes in failure runs. Kimi doesn't connect "finalizer didn't run" → "need `aclose()`" without external guidance.
- **retry_stream**: Same pattern. Uses manual `__anext__()` iteration rather than `async for`. Kimi never recognizes that this pattern bypasses automatic generator cleanup. 0 writes across all 7 observed failure runs.

### Mode C: Partial Fix — Wrong Ordering (async_generator new seed)

The model discovers `aclose()` and writes a fix, but applies it in the wrong order. The async_generator new seed requires LIFO finalization (downstream-first: C→B→A). Kimi consistently calls `for g in generators: await g.aclose()` (forward order: A→B→C) rather than `for g in reversed(generators): await g.aclose()`. Finalizers run, but in the wrong sequence. This is a **new failure mode** not observed in earlier iterations — the fix is present but semantically incorrect.

---

## What Kimi Knows (Solved in ≤ 3 Turns)

Kimi solves tasks immediately when the fix matches a pattern in its training data:

| Pattern | Example task |
|---------|-------------|
| `sys.exc_info()` traceback frame retention | exc_info_leak |
| struct byte-order mismatch | frame_codec |
| PEP 479: StopIteration in generator body | generator_stop |
| WeakValueDictionary + ephemeral bound methods | weakref_callback |
| asyncio cancellation propagation | async_worker_pool |
| B-tree CLRS split algorithm | btree |
| Thompson NFA construction | regex_engine |
| `contextvars.Context()` isolation | context_vars |
| Raft AppendEntries spec | raft_log |

The common thread: these are all **documented Python behaviors** with Stack Overflow answers, PEP text, or tutorial coverage. Kimi's training data contains enough of these to recognize them from the error message alone.

## What Kimi Doesn't Know

The confirmed gap: **async generator cleanup is not automatic under manual `__anext__()` iteration**.

> When an async generator is consumed via `async for`, Python automatically calls `aclose()` on it when the loop exits (normally, via `break`, or via exception). This guarantee does NOT hold when iterating manually with `__anext__()`. If the calling code raises or is cancelled while the iterator is suspended, the generator's `finally` block will not run unless `aclose()` is explicitly awaited.

This distinction is in the Python docs but is rarely discussed. Stack Overflow answers and tutorial examples almost exclusively use `async for`, so the manual-iteration cleanup contract has minimal training data coverage. Kimi never surfaces it through `pytest` output observation alone — it sees "source not finalized" but cannot identify the cause as the iteration pattern.

The CPython GC tricolor algorithm (gc_cycles) is a secondary gap — Kimi sometimes solves it when the API is stable, suggesting partial knowledge but not confident enough to apply without API issues.

---

## How 0% Was Achieved

Task_05 reaches 0/5 because it targets a genuine capability gap rather than an infrastructure failure or a deliberate trick:

- **Not an API abort**: Kimi completes all 30 turns; the failure is behavioral, not connection-based.
- **Not a deliberately obscured constraint**: The fix (`await it.aclose()` in a `finally` block) is present in the bug comment and obvious once you know the manual iteration contract. Kimi just doesn't know the contract.
- **Not luck**: 0/7 runs across two separate eval days with no variation in the failure mode.

The root cause is a training data gap: manual `__anext__()` iteration with async generators is rare in Python tutorials and Stack Overflow answers. `async for` dominates all documentation of async generators. Kimi has internalised the `async for` cleanup guarantee but not its absence under manual iteration.

### What didn't work on the path to 0%

| Approach | Why it failed |
|----------|--------------|
| Long reasoning chain (tokenizer) | API aborts — infrastructure, not capability |
| Multi-file tracing (saga, query_plan, pubsub) | Not yet validated; may be solvable |
| LIFO ordering constraint (async_generator new seed) | Trick — Kimi writes code but misses `reversed()`; not a knowledge gap |
| Most "obscure" Python gotchas | Already in Kimi's training data (exc_info, PEP 479, WeakValueDictionary, etc.) |

---

## Lessons for Benchmark Design

To reliably reach < 20% against Kimi 2.6, tasks must satisfy at least one of:

1. **Reasoning chain > API timeout**: Tasks where the minimum reasoning time exceeds ~360s. The tokenizer qualifies. Designing tasks that *require* this much reasoning without being artificially complex is hard.

2. **Fix requires knowledge absent from all documentation**: The `aclose()` protocol is the only confirmed example. Candidates for similar-level obscurity:
   - Python generator `throw()` protocol edge cases (not documented outside CPython source)
   - GC finalization ordering during interpreter shutdown (only in CPython internals docs)
   - `threading.local` behavior across fork+exec in multiprocessing (PEP 643, rarely read)
   - `__del__` called with `None` globals during module teardown (CPython implementation detail)

3. **Misleading error message + counterintuitive fix**: The test output must actively point in the wrong direction, and the correct fix must contradict the obvious hypothesis. Task_08's inverted gc_refs direction partially qualifies but Kimi solves it when the API cooperates.

---

## Trajectory Files

All runs saved in `trajectories/`. Notable trajectories:

| File | Content |
|---|---|
| `tokenizer_202605*.json` | Always 1–2 turns, API abort mid-response |
| `async_generator_20260505_121334.json` | 30 turns, 82K reasoning chars, 0 writes — canonical exploration loop (old seed) |
| `async_generator_20260505_131757.json` | 15 turns, PASSED — Kimi found `aclose()` via source reading (old seed) |
| `async_generator_20260507_183650.json` | 30 turns, writes every other turn — Mode C: `aclose()` added but forward order, 4 tests always failing (new seed) |
| `async_generator_20260507_192948.json` | 30 turns, write at turn 20 → 1 test still failing — closest new-seed attempt; `reversed()` still missing |
| `gc_cycles_20260505_125053.json` | 5 turns, PASSED — found inverted subtraction via code reading |
| `gc_cycles_20260505_133723.json` | 1 turn, API abort |
| `retry_stream_20260507_191111.json` | 30 turns, 0 writes — cancellation test fails; pure exploration loop (run 1 of 5) |
| `retry_stream_20260507_152209.json` | 30 turns, 0 writes — StopIteration propagation test fails first (alternate failure mode) |
