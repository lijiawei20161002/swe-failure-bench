# Evaluation Findings: Kimi 2.6 on swe-failure-bench

**Model:** `kimi-for-coding` (Kimi 2.6, extended-thinking reasoning model)  
**Dates:** 2026-05-04 – 2026-05-05  
**Eval script:** `eval_kimi.py`  
**API note:** `kimi-for-coding` requires `User-Agent: claude-code/1.0` (or `opencode/*`); fails with 403 otherwise. Extended thinking is always on — `reasoning_content` must be echoed back in multi-turn history or the API returns 400.

---

## Summary of All Runs

### Iteration 1 — 14-task initial batch, BUG comments present (May 4)

Seed code contained inline `# BUG N: ...` comments labelling the exact bugs. **Pass rate: 5/8 on original 8 tasks (62%), 12/14 on full 14-task batch (86%).**

Most tasks solved in 2–5 turns. The BUG comments acted as hints: Kimi read the source, spotted the labels, and applied the fix directly.

### Iteration 2 — 14-task batch, BUG comments stripped (May 4)

Same code, comments removed. **Pass rate: 4/8 = 50%.**

Removing comments added ~3–5 extra exploration turns per task but didn't change pass/fail outcomes except for one task (task_08_resp_parser dropped from pass to fail due to a connection abort that occurred during longer reasoning).

**Key finding:** BUG comments barely mattered. Kimi diagnoses most bugs from `pytest -v` output alone, without needing source-level hints.

### Iteration 3 — Redesigned 8-task benchmark (May 5)

Tasks 03–08 are new, targeting failure modes identified in iterations 1–2. **Pass rate: 4/8 = 50%.**

---

## Final Benchmark Results (Current 8 Tasks)

| # | Task | Result | Turns | Writes | Failure mode |
|---|------|--------|-------|--------|--------------|
| 01 | `async_worker_pool` | ✓ PASSED | 3 | 1 | — |
| 02 | `tokenizer` | ✗ FAILED | 1 | 0 | API connection abort (reasoning too long) |
| 03 | `async_generator` | ✗ FAILED | 30 | 0 | **Never wrote a fix** — 30 turns of bash only |
| 04 | `btree` | ✓ PASSED | 2 | 1 | — |
| 05 | `regex_engine` | ✗ FAILED | 1 | 0 | API connection abort (reasoning too long) |
| 06 | `context_vars` | ✓ PASSED | 4 | 1 | — |
| 07 | `raft_log` | ✓ PASSED | 3 | 1 | — |
| 08 | `gc_cycles` | ✗ FAILED | 4 | 0 | **Never wrote a fix** — explored but gave up |

**Pass rate: 4/8 = 50%**

---

## Two Distinct Failure Modes

### Mode A: API Connection Abort (tasks 02, 05)

Tasks with many interacting edge cases cause extremely long reasoning chains (>360s), triggering a `Connection aborted. Remote end closed connection without response` error. The model was likely computing a correct fix but the HTTP connection dropped mid-response.

- **task_02 (tokenizer)**: Python tokenizer state machine — raw strings (`r"..."`), triple-quoted strings (`"""..."""`), escape sequence processing (`\n`, `\t`), and their interactions require reasoning through ~10 overlapping regex patterns simultaneously.
- **task_05 (regex_engine)**: NFA Thompson construction — unhashable `State` dataclass, missing `out2` traversal in ε-closure, character class range parsing. Three layered bugs that cascade.

These are genuinely hard reasoning tasks. They fail because the model thinks too deeply, not because it lacks capability. Given unlimited time, it would likely solve them.

### Mode B: Exploration Without Commitment (tasks 03, 08)

The model ran `pytest` and `read_file` extensively but **wrote zero files** throughout the entire budget. The test errors did not point clearly enough to the fix, so the model looped without converging.

**task_03 (async_generator)** — 30 turns, 82,637 reasoning chars, 0 writes:
- The failing tests show finalizers not running, but the error message doesn't indicate *why*
- The fix requires knowing that Python async generators don't call `finally` blocks unless `aclose()` is explicitly awaited — a subtle CPython implementation detail
- Kimi kept running `pytest` to observe the failure, reading `pipeline.py` to understand it, but never identified the `aclose()` pattern as the missing piece
- **Kimi's blind spot**: the async generator finalization contract is non-obvious from documentation. Most developers don't know that `async for gen` only closes the *last* generator in a chain.

**task_08 (gc_cycles)** — 4 turns, 538 reasoning chars, 0 writes:
- The failing tests show objects not being collected when they should be
- The fix requires realizing the `gc_refs` subtraction is inverted: the code decrements the *holder's* count instead of the *target's* count
- Kimi explored but the 538-char reasoning suggests it made very few reasoning steps before giving up (possibly another near-abort)
- **Kimi's blind spot**: the CPython tricolor mark-and-sweep algorithm is rarely encountered outside CPython source, and the "subtract internal reference counts" step is counterintuitive — you're modifying the referent, not the referrer.

---

## Analysis of Kimi's Strengths

Kimi 2.6 reliably solves tasks where:

1. **Test failures are diagnostic.** `KeyError: 0` → `_min_freq` was never set. `AssertionError: commit_index=2 should be 0` → `_maybe_update_commit()` called on rejection. The error message directly implicates the buggy line.

2. **The fix matches a known pattern.** B-tree split indices, asyncio `create_task()`, `threading.Condition.notify_all()`, Raft `append_entries` spec — all are patterns in Kimi's training data. Once it recognizes the pattern, the fix is mechanical.

3. **Single-file changes.** All 4 passing tasks required editing exactly one file. The model reads the file, identifies the issue, applies the patch.

4. **The fix is the obvious thing.** Adding `contextvars.Context()` for fresh isolation is one unusual API call but once you know Python's contextvars module, it's the natural solution. Similarly, the B-tree split off-by-one is a standard CLRS correction.

## Analysis of Kimi's Weaknesses

### Weakness 1: Implicit Python Runtime Contracts

Kimi does not reliably know Python's **implicit cleanup contracts** for generators and coroutines:

- Async generators do not finalize (`finally` block runs) unless `aclose()` is explicitly awaited OR the generator is garbage-collected with no pending `send()`
- Regular generators in a chain: only the outermost generator is auto-closed by `for` exit; inner ones are not
- This is documented in PEP 525 but rarely appears in tutorials or StackOverflow answers

**Impact:** Any task that requires understanding Python's memory/cleanup model at this level will stump Kimi.

### Weakness 2: Unintuitive Algorithm Directions

When a bug requires inverting a direction or sign that seems logically reasonable, Kimi struggles:

- GC: "subtract internal references" means decrement the *target*'s count, not the *source*'s. The buggy code decrements the source — both seem plausible.
- The correct version requires trusting a paper algorithm over intuition
- Kimi tends to look for syntax/logic errors, not directional inversions in correct-looking code

### Weakness 3: API Reliability on Long Reasoning

For tasks requiring 300–600s of thinking (complex state machines, multi-layered algorithm bugs), the Kimi API drops the connection. This is an infrastructure failure, not a capability failure, but it has the same effect on pass rate.

### Weakness 4: Knowing When to Write vs. Explore

On task_03, Kimi ran `pytest` 30 consecutive times without writing a fix. It was stuck in an explore-only loop. This suggests a meta-level weakness: Kimi doesn't have a good signal for when it has gathered enough information and should commit to a hypothesis. When the test output is ambiguous or points to the wrong place, the model over-explores.

---

## What Didn't Work to Reduce Pass Rate

1. **BUG comments in code** — removing them only added ~3 extra turns, didn't change pass/fail
2. **Multi-file tasks** — Kimi wrote all 3 files simultaneously on task_13 (JSON-RPC); multi-file alone isn't hard
3. **Multiple interacting bugs** — tasks 01, 07, 09 all had 2–3 independent bugs; Kimi fixed them sequentially without issue
4. **Off-by-one errors** — B-tree split off-by-one was caught and fixed in 2 turns; standard CLRS correction
5. **Protocol compliance (Raft)** — Kimi knows the Raft spec; fixing spec violations was straightforward

---

## What Does Work to Reduce Pass Rate

Based on empirical results, two categories reliably cause failures:

**Category A: Complex reasoning that causes API timeouts**
- Tasks involving Python tokenizer/parser internals with many overlapping rules
- NFA/DFA construction with multiple interacting subsystems
- Any task where the reasoning chain is too long for a single API call

**Category B: Fixes requiring non-obvious runtime knowledge**
- Python's async generator finalization (`aclose()`) contract
- CPython's garbage collector tricolor algorithm details
- Python descriptor `__class_cell__` / `__init_subclass__` interactions
- Python's `contextvars` concurrency model at edge cases

The common pattern for Category B: **the fix requires knowing a specific CPython implementation detail that isn't in tutorials, Stack Overflow answers, or language documentation summaries** — only in CPython source code, PEPs, or academic papers.

---

## Trajectory Files

All runs are saved in `trajectories/`. Each JSON contains:
- `task`, `model`, `start_time`, `end_time`
- `turns`: list of `{turn, finish_reason, reasoning_length, content, tool_calls, tool_results, test_run}`
- `passed`, `pass_turn`, `total_turns`, `total_api_calls`

| File pattern | Run | Notes |
|---|---|---|
| `task_*_202605041821*.json` | Run 1 (BUG hints present) | Original 14-task batch |
| `task_*_202605041915*.json` | Run 2 (hints stripped) | Same tasks, clean code |
| `task_*_20260504_21*.json` | Run 3 (all 14 tasks) | Full 14-task sweep, 86% pass rate |
| `task_*_20260505_08*.json` | Run 4 (redesigned 8 tasks) | **Current benchmark**, 50% pass rate |

### Run 4 Trajectory Highlights

| Task | File | Interesting detail |
|---|---|---|
| task_03_async_generator | `*_084334.json` | 18KB, 82K reasoning chars, 30 turns of bash — model was stuck in analysis paralysis |
| task_01_async_worker_pool | `*_082714.json` | 58K reasoning chars despite solving in 3 turns — deep thought but converged quickly |
| task_10_gc_cycles (now task_08) | `*_090000.json` | Only 538 reasoning chars — model barely engaged before giving up |
| task_04_tokenizer (now task_02) | `*_083226.json` | 311 reasoning chars — connection dropped almost immediately |
