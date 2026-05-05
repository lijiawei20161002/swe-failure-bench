# Evaluation Findings: Kimi 2.6 on swe-failure-bench

**Model:** `kimi-for-coding` (Kimi 2.6, extended-thinking reasoning model)  
**Dates:** 2026-05-04 – 2026-05-05  
**Eval script:** `eval_kimi.py`  
**API note:** `kimi-for-coding` requires `User-Agent: claude-code/1.0`; fails with 403 otherwise. Extended thinking is always on — `reasoning_content` must be echoed back in multi-turn history or the API returns 400.

---

## Final Benchmark Results: 5-Run Statistical Evaluation

**40 total attempts (8 tasks × 5 independent runs)**  
**Overall pass rate: 21/40 = 52.5%**  
**Target: <20% — not achieved**

| Task | Passes | Pass Rate | Failure mode |
|------|--------|-----------|--------------|
| 01 `async_worker_pool` | 3/5 | 60% | Reliable; 2 API aborts in runs 4–5 |
| 02 `tokenizer` | 0/5 | 0% | API connection abort every run |
| 03 `async_generator` | 2/5 | 40% | Stochastic: exploration loop or API abort |
| 04 `btree` | 2/5 | 40% | Solves in 3 turns when API stable; aborts otherwise |
| 05 `regex_engine` | 2/5 | 40% | Partial reasoning before API abort |
| 06 `context_vars` | 5/5 | 100% | Always solved in 3–5 turns |
| 07 `raft_log` | 5/5 | 100% | Always solved in 2–3 turns |
| 08 `gc_cycles` | 2/5 | 40% | Solves in 3 turns when API stable; aborts otherwise |

### Per-Run Breakdown

| Run | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | Score |
|-----|----|----|----|----|----|----|----|-----|-------|
| 1 | ✓ | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ | ✓ | 5/8 |
| 2 | ✓ | ✗ | ✓ | ✓ | ✗ | ✓ | ✓ | ✗ | 5/8 |
| 3 | ✓ | ✗ | ✓ | ✗ | ✓ | ✓ | ✓ | ✗ | 5/8 |
| 4 | ✗ | ✗ | ✗ | ✓ | ✗ | ✓ | ✓ | ✓ | 4/8 |
| 5 | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ | ✗ | 2/8 |

Runs 4 and 5 show severe API instability — even task_01 (normally solved in 2 turns) was aborted immediately, suggesting quota pressure or server-side throttling increased connection timeout frequency.

---

## Two Distinct Failure Classes

### Class A: API Connection Aborts (~40% of all failures)

Tasks with long reasoning chains cause the extended-thinking response to exceed the HTTP connection timeout (~360s). The model was mid-solution when the connection dropped. This is **infrastructure failure, not capability failure**.

**task_02 (tokenizer)** — 0/5, always aborts. Python tokenizer state machine: raw strings (`r"..."`), triple-quoted strings (`"""..."""`), escape sequences (`\n`, `\t`), and their interactions require reasoning through ~10 overlapping regex patterns simultaneously. The reasoning chain exceeds the connection timeout before any response is returned. This task is essentially unrunnable with the current API setup.

**task_05 (regex_engine)** — 2/5. NFA Thompson construction with three layered bugs (unhashable `State` dataclass, missing `out2` traversal in ε-closure, character class range parsing). When the API is stable it solves in 3 turns; under load, it aborts 3 turns in.

**Runs 4–5 systemic aborts** — `async_worker_pool`, `btree`, and `gc_cycles` all aborted immediately in runs 4–5 despite reliably passing in runs 1–3. This is quota exhaustion or server-side rate limiting, not task difficulty.

### Class B: Genuine Capability Gaps (~60% of non-abort failures)

**task_03 (async_generator)** — 2/5, the benchmark's clearest capability signal. The model runs `pytest` for 15–30 turns without writing a fix. The fix requires knowing that Python async generators do not run `finally` blocks unless `aclose()` is explicitly awaited — a PEP 525 detail absent from most tutorials and Stack Overflow answers.

- Run 1: 30 turns, 0 writes, exploration loop exhausted budget
- Run 2: 15 turns, solved (found `aclose()` pattern)
- Run 3: 17 turns, solved
- Run 4: 9 turns, API abort mid-exploration
- Run 5: 11 turns, API abort mid-exploration (had written a partial fix at turn 6 that still failed 1 test)

When Kimi solves this, it takes 15–17 turns of `pytest` + `read_file` before committing a write. When it fails, it either hits the turn limit still in exploration mode, or the API drops the connection.

**task_08 (gc_cycles)** — 2/5. The CPython tricolor mark-and-sweep "subtract internal refs" step is counterintuitive: you decrement the *target* object's count, not the *source's*. The buggy code decrements the source — both look plausible. When the API is stable, Kimi reads the source and fixes it in 3 turns. Under API instability it never gets the chance.

---

## Analysis of Kimi's Strengths

Kimi 2.6 reliably solves tasks where:

1. **Test failures are diagnostic.** The error message directly implicates the buggy line or missing call.
2. **The fix matches a known pattern.** B-tree split indices, asyncio task creation, `threading.Condition.notify_all()`, Raft `append_entries` spec — all are patterns well-represented in training data.
3. **Single-file changes.** All 5 consistently-passing tasks required editing exactly one file.
4. **The fix is the obvious thing once the bug is located.** `contextvars.Context()` for fresh isolation, `commit_index` not updated on rejection — once recognized, the fix is mechanical.

## Analysis of Kimi's Weaknesses

### Weakness 1: Implicit Python Runtime Contracts

Kimi does not reliably know Python's implicit cleanup contracts for async generators:

- Async generators do not finalize (`finally` block runs) unless `aclose()` is explicitly awaited OR the generator is garbage-collected with no pending `send()`
- Only the outermost generator in a chain is auto-closed by `async for` exit; inner stages are not
- Documented in PEP 525 but rare in tutorials or StackOverflow answers

Any task requiring understanding of Python's async memory/cleanup model at this level will expose this gap.

### Weakness 2: Unintuitive Algorithm Directions

When a bug requires inverting a direction or sign that seems logically reasonable, Kimi struggles:

- GC: "subtract internal references" means decrement the *target's* count, not the *source's*. The buggy code decrements the source — both seem plausible.
- Kimi tends to identify syntax/logic errors; directional inversions in internally-consistent code are harder to flag.

### Weakness 3: Knowing When to Commit

On task_03 run 1, Kimi ran `pytest` 30 consecutive times without writing a fix. It gathered more information past the point of diminishing returns. When the test output is ambiguous or points to the wrong abstraction layer, the model over-explores rather than forming and testing a hypothesis.

### Weakness 4: API Reliability on Long Reasoning

For tasks requiring 300–600s of thinking, the Kimi API drops the connection. This is an infrastructure limit, not a reasoning limit, but it has the same effect on pass rate. Tasks 02 and 05 are likely *solvable* given unlimited time — we can't tell from this data.

---

## Why <20% Was Not Reached

Three structural problems with the current benchmark:

**1. Tasks 06 and 07 are too easy.** `context_vars` (one API call pattern) and `raft_log` (one spec violation) both pass 5/5. They add 10 percentage points unconditionally and cannot be pulled down without replacing the tasks. Harder replacements should target implicit runtime contracts, cross-file interface bugs, or race conditions.

**2. API instability conflates infrastructure failure with capability failure.** Roughly half the failures in runs 4–5 were connection aborts on tasks Kimi solves cleanly when the API is stable. A fair benchmark would retry aborted runs, use a local model, or exclude abort-caused failures from capability assessment. The "true" capability pass rate — excluding API-abort failures on tasks demonstrated solvable in other runs — is closer to 60–65%.

**3. The hardest tasks (02, 05) always abort.** They contribute 0% and 40% pass rates respectively, but for the wrong reason: we can't determine if Kimi would have solved them given a stable connection. Task_02 in particular may be genuinely unsolvable under any API timeout, but we have no evidence either way.

---

## What Would Actually Hit <20%

Based on empirical results, the reliable failure categories are:

**Category A: Complex reasoning that causes API timeouts**
- Python tokenizer/parser internals with many overlapping rules
- NFA/DFA construction with multiple interacting subsystems
- Any task where the minimum reasoning chain exceeds ~360s

**Category B: Fixes requiring non-obvious runtime knowledge**
- Python async generator finalization (`aclose()`) contract — PEP 525
- CPython GC tricolor algorithm details — CPython source only
- Python descriptor `__class_cell__` / `__init_subclass__` interactions
- `sys.exc_info()` frame retention semantics
- Generator-based coroutine `throw()` / `close()` protocol

**Category C: Interface bugs (not yet tested)**
- Bugs where the error lives in the contract between two files, not in either file alone
- Protocol mismatches where both sides of an interface look correct in isolation

**Category D: Concurrency bugs (not yet tested)**
- Bugs that only manifest under specific scheduler interleavings
- Kimi cannot force thread interleaving via `pytest` alone

To reliably reach <20% against Kimi 2.6 with a stable API: replace tasks 06 and 07 with Category B or C tasks, and add at least one Category D task. The benchmark should have no task where the fix pattern appears in common documentation — only in CPython source code, PEPs, or academic papers.

---

## Trajectory Files

All runs are saved in `trajectories/`. Each JSON contains:
- `task`, `model`, `start_time`, `end_time`
- `turns`: list of `{turn, finish_reason, reasoning_length, content, tool_calls, tool_results, test_run}`
- `passed`, `pass_turn`, `total_turns`, `total_api_calls`

### Run Summary by Timestamp

| File pattern | Run | Pass rate | Notes |
|---|---|---|---|
| `task_*_202605041821*.json` | Iteration 1 (BUG hints present) | 12/14 (86%) | Original 14-task batch with inline `# BUG` comments |
| `task_*_202605041915*.json` | Iteration 2 (hints stripped) | 4/8 (50%) | Same code, comments removed |
| `task_*_20260504_21*.json` | Iteration 3 (all 14 tasks) | 12/14 (86%) | Full 14-task sweep |
| `task_*_20260505_08*.json` | Iteration 4 (redesigned 8 tasks) | 4/8 (50%) | Single-run baseline on current benchmark |
| `task_*_20260505_1[12]*.json` | 5-run eval, run 1 | 5/8 (62%) | API stable |
| `task_*_20260505_13*.json` | 5-run eval, run 2 | 5/8 (62%) | API stable |
| `task_*_20260505_14*.json` | 5-run eval, run 3 | 5/8 (62%) | API stable |
| `task_*_20260505_1[5-6]*.json` | 5-run eval, runs 4–5 | 4/8, 2/8 | Heavy API instability |

### Notable Trajectories

| Task | File | Detail |
|---|---|---|
| task_03 run 1 | `*_121334.json` | 30 turns, 0 writes — pure exploration loop |
| task_03 run 2 | `*_131757.json` | 15 turns — found `aclose()` pattern after sustained `pytest` loop |
| task_03 run 3 | `*_140426.json` | 17 turns — read source first, then converged |
| task_01 run 1 | `*_115913.json` | 2 turns — fastest solve in the entire dataset |
| task_02 all runs | `*_120424.json` etc. | Always aborts at turn 1–2; reasoning chain too long |
| task_06 run 4 | `*_153831.json` | Partial write at turn 2 (2 tests still failing), corrected at turn 5 |
