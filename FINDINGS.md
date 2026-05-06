# Evaluation Findings: Kimi 2.6 on swe-failure-bench

**Model:** `kimi-for-coding` (Kimi 2.6, extended-thinking reasoning model)  
**Dates:** 2026-05-04 – 2026-05-06  
**Eval script:** `eval_kimi.py`  
**API note:** `kimi-for-coding` requires `User-Agent: claude-code/1.0`; fails with 403 otherwise. Extended thinking is always on — `reasoning_content` must be echoed back in multi-turn history or the API returns 400.

---

## Current Benchmark: 3 Tasks

These are the tasks that survived empirical elimination — everything Kimi solved reliably was removed.

| Task | Seed file | Pass rate (5 runs) | Failure mode |
|------|-----------|-------------------|--------------|
| 02 tokenizer | `task_02_tokenizer/tokenizer.py` | 0/5 (0%) | API abort every run |
| 03 async_generator | `task_03_async_generator/pipeline.py` | 2/5 (40%) | Exploration loop — never discovers `aclose()` |
| 08 gc_cycles | `task_08_gc_cycles/ref_graph.py` | 2/5 (40%) | API abort or inverted gc_refs direction |

**Overall observed pass rate: ~28–57%** (varies by API reliability)

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

---

## Two Confirmed Failure Modes

### Mode A: API Connection Abort (task_02, task_08 sometimes)

Tasks requiring long reasoning chains (>~360s) cause the HTTP connection to drop mid-response. This is **infrastructure failure, not capability failure** — the model was likely computing a correct fix.

- **task_02 (tokenizer)**: Python tokenizer state machine — raw strings, triple-quoted strings, escape sequences, and their interactions. ~10 overlapping rules require simultaneous reasoning. Aborts 5/5 runs.
- **task_08 (gc_cycles)**: Sometimes aborts under API load; sometimes solves in 3 turns when the API is stable.

### Mode B: Exploration Loop Without Commitment (task_03)

The model runs `pytest` for 15–30 turns without writing a fix. The test output points to a symptom (finalizers not running) but not the cause (missing `aclose()`).

- **task_03 (async_generator)**: 30 turns of `run_bash`, 0 writes in failure runs. The `aclose()` protocol is in PEP 525 but not in tutorials or StackOverflow answers. Kimi doesn't connect "finalizer didn't run" → "need `aclose()`" without external guidance.

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

The confirmed gap: **Python's async generator finalization contract** (PEP 525).

> When an `async for` loop over an async generator exits (normally, via exception, or via `break`), only the *outermost* generator is automatically closed. Inner generators in a chained pipeline are not. Their `finally` blocks do not run unless `aclose()` is explicitly awaited on each one.

This is documented in PEP 525 but does not appear in tutorials, StackOverflow answers, or `asyncio` documentation summaries. Kimi never discovers it through `pytest` output observation alone.

The CPython GC tricolor algorithm (task_08) is a secondary gap — Kimi sometimes solves it when the API is stable, suggesting it has partial knowledge but not confident enough to apply it without API issues.

---

## Why < 20% Has Not Been Achieved

### Root cause 1: Task_02 is an infrastructure failure, not a capability failure

Kimi aborts on tokenizer 5/5 times because the reasoning chain is too long for the HTTP timeout. If the API were reliable (or if we used a local model), Kimi would likely solve this. It contributes 0% pass rate for the wrong reason.

### Root cause 2: Only one confirmed true capability gap (task_03)

Task_03 fails because of genuine missing knowledge (the `aclose()` protocol). This is the only task in the benchmark that tests capability rather than infrastructure. Its pass rate of 2/5 is high enough to prevent reaching < 20% even if everything else failed.

### Root cause 3: Most "obscure" Python knowledge is in Kimi's training data

Patterns that seemed obscure (exc_info traceback retention, PEP 479, WeakValueDictionary + bound methods) turned out to be well-represented in Kimi's training data. The model solved all of them immediately without hesitation.

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

| File pattern | Content |
|---|---|
| `task_02_tokenizer_202605*.json` | Always 1–2 turns, API abort mid-response |
| `task_03_async_generator_20260505_121334.json` | 30 turns, 82K reasoning chars, 0 writes — canonical exploration loop |
| `task_03_async_generator_20260505_131757.json` | 15 turns, PASSED — Kimi found `aclose()` via source reading |
| `task_08_gc_cycles_20260505_125053.json` | 5 turns, PASSED — found inverted subtraction via code reading |
| `task_08_gc_cycles_20260505_133723.json` | 1 turn, API abort |
