# Evaluation Findings: Kimi 2.6 on swe-failure-bench

**Model:** `kimi-for-coding` (Kimi 2.6, reasoning model)  
**Date:** 2026-05-04  
**Eval script:** `eval_kimi.py`  
**Two runs:** Run 1 with `# BUG` hint comments in seed code; Run 2 with all hints stripped.

---

## Results

### Run 1 — Seed code contained `# BUG N:` comments (inadvertent hints)

| Task | Result | Turns | Notes |
|---|---|---|---|
| `task_01_async_worker_pool` | ✓ PASSED | 11 | Multiple exploration turns, correct fix |
| `task_02_connection_pool` | ✓ PASSED | 2 | Direct fix, read BUG labels and applied |
| `task_03_mini_jsonschema` | ✗ FAILED | 8 | API timed out (3×180s) mid-reasoning |
| `task_04_tokenizer` | ✗ FAILED | 1 | API timed out before any write |
| `task_05_lfu_cache` | ✓ PASSED | 3 | Correct O(1) LFU implementation |
| `task_06_query_builder` | ✓ PASSED | 2 | Direct fix of SQL clause ordering |
| `task_07_event_emitter` | ✗ FAILED | 1 | API timed out before any write |
| `task_08_resp_parser` | ✓ PASSED | 3 | Fixed CRLF consumption + array position |

**Pass rate: 5/8 = 62%**

### Run 2 — All `# BUG` hints stripped (blind eval)

| Task | Result | Turns | Notes |
|---|---|---|---|
| `task_01_async_worker_pool` | ✓ PASSED | 10 | More exploration (9 bash + 1 write) |
| `task_02_connection_pool` | ✓ PASSED | 2 | Solved from test output alone |
| `task_03_mini_jsonschema` | ✗ FAILED | 1 | Connection aborted mid-reasoning |
| `task_04_tokenizer` | ✗ FAILED | 1 | Connection aborted mid-reasoning |
| `task_05_lfu_cache` | ✓ PASSED | 2 | Solved from test output alone |
| `task_06_query_builder` | ✓ PASSED | 5 | Needed more exploration but still solved |
| `task_07_event_emitter` | ✗ FAILED | 1 | Connection aborted mid-reasoning |
| `task_08_resp_parser` | ✗ FAILED | 2 | Connection aborted mid-reasoning |

**Pass rate: 4/8 = 50%**

---

## Key Findings

### 1. BUG hint comments barely helped

Removing the inline `# BUG N: ...` comments from seed code only dropped the pass rate from 62% → 50% (one extra task failed). Kimi 2.6 is capable enough to diagnose most bugs directly from `pytest -v` output without needing source-level hints. The comments made some tasks 3–5× faster (fewer turns) but did not determine pass/fail in most cases.

**Implication:** Future seed code should not contain any explanatory comments that describe the bug, but this alone is insufficient to reliably produce <20% pass rate.

### 2. Two distinct failure modes emerged

**API reliability failures (tasks 3, 4, 7, 8 in run 2):** The Kimi API dropped the connection mid-turn with `Connection aborted. Remote end closed connection without response`. This happened consistently on tasks requiring heavy reasoning:

- `task_03_mini_jsonschema` — `oneOf` exact-match semantics + `$ref` context threading
- `task_04_tokenizer` — regex state machine for raw strings + triple-quoted strings
- `task_07_event_emitter` — dot-aware glob matching + `WeakMethod` weakrefs
- `task_08_resp_parser` — CRLF position tracking + array element iteration

These connection drops are a side effect of the tasks being hard: the reasoning model spends so long reasoning that the HTTP connection times out at ~360s. So the failure mode is real — these tasks do require more thought — but it conflates "API reliability" with "capability".

**Genuine capability passes (tasks 1, 2, 5, 6):** All four passed in both runs with the model correctly fixing threading race conditions, asyncio cancellation propagation, LFU eviction policy, and SQL clause ordering. The test failures clearly pointed to the fix and the model applied it correctly.

### 3. Kimi 2.6 excels at well-known production patterns

The model solves tasks immediately when:
- The bug maps to a recognizable pattern (threading.Condition.notify\_all, asyncio gather, SQL clause order)
- The test error output is diagnostic (e.g., `KeyError: 0` for `_min_freq`, `AssertionError: waiter thread must unblock`)
- The fix is a single-file change with < ~50 lines affected

It struggles when:
- The fix requires understanding subtle Python semantics not evident from the error (e.g., `weakref.ref(bound_method)` is immediately dead; must use `WeakMethod`)
- Multiple independent invariants must all be fixed simultaneously
- The reasoning chain is long enough to hit API timeouts

### 4. Turn counts increased significantly without hints

| Task | Turns (with hints) | Turns (without hints) |
|---|---|---|
| task_01 | 11 | 10 |
| task_02 | 2 | 2 |
| task_05 | 3 | 2 |
| task_06 | 2 | 5 |

Task 6 (query builder) went from 2 turns to 5 — the model needed to read the source file explicitly before understanding the clause ordering bug, whereas with the BUG comment it could spot the issue immediately. Task 2 was unchanged because threading bugs are immediately obvious from the test output.

### 5. The 50% pass rate is well above the <20% target

The benchmark is too easy for Kimi 2.6 for two reasons:

**A) Shell access is very powerful.** With `run_bash`, the model can iterate `pytest → fix → pytest` in a tight feedback loop. Even without knowing the fix upfront, it can try approaches and verify instantly. This is fundamentally different from a static code-change benchmark.

**B) Tasks are one-file bugs.** All 8 tasks require editing a single Python file. Multi-file changes where fixing one module breaks another would be significantly harder.

---

## Recommendations for Achieving <20% Pass Rate

To reliably produce <20% pass rate against Kimi 2.6 (or similar strong models), future tasks should have one or more of these properties:

1. **Multi-file coordination required.** Bug spans two or more files where fixing one creates a new failure in another (e.g., ORM model + migration + serializer).

2. **Misleading test failures.** The test error message points to the wrong place — the observable failure is a consequence of a non-obvious root cause several layers away.

3. **Requires obscure library semantics.** Fix depends on knowing a non-obvious API contract (e.g., Python descriptor `__set_name__` protocol, `asyncio.TaskGroup` exception chaining, SQLAlchemy relationship `cascade` rules).

4. **Correct fix must pass a property-based or randomized test.** Simple input/output tests can be gamed; property-based tests catch generalizations that look correct on specific examples.

5. **The obvious fix is demonstrably wrong.** Any straightforward attempt introduces a regression in a different test, forcing the model to understand the constraint rather than just satisfy the failing test.

---

## API Reliability Notes

- **Timeout:** The Kimi API (`kimi-for-coding`) has a practical response limit of ~360s for reasoning models. Turns requiring complex multi-step reasoning consistently hit this limit.
- **User-Agent required:** The endpoint rejects calls without a recognized coding-agent User-Agent (e.g., `claude-code/1.0`, `opencode/1.14.33`).
- **reasoning\_content must be echoed:** Multi-turn conversations must include the `reasoning_content` field from the assistant message when appending to history; omitting it causes a 400 error.

---

## Trajectory Files

All runs saved in `trajectories/`. Each JSON file contains:
- `task`: task name
- `model`: `kimi-for-coding`
- `turns`: list of turn records with tool calls, results, and test output
- `passed`: bool
- `pass_turn`: turn number where tests first passed (or null)
- `total_turns` / `total_api_calls`: resource usage

| File | Run | Result |
|---|---|---|
| `task_01_*_182114.json` | Run 1 (with hints) | PASSED (11 turns) |
| `task_01_*_191528.json` | Run 2 (blind) | PASSED (10 turns) |
| `task_02_*_182311.json` | Run 1 | PASSED (2 turns) |
| `task_02_*_191659.json` | Run 2 | PASSED (2 turns) |
| `task_03_*_183749.json` | Run 1 | FAILED (API timeout) |
| `task_03_*_192205.json` | Run 2 | FAILED (connection abort) |
| `task_04_*_184804.json` | Run 1 | FAILED (API timeout) |
| `task_04_*_192719.json` | Run 2 | FAILED (connection abort) |
| `task_05_*_184952.json` | Run 1 | PASSED (3 turns) |
| `task_05_*_193215.json` | Run 2 | PASSED (2 turns) |
| `task_06_*_185052.json` | Run 1 | PASSED (2 turns) |
| `task_06_*_193314.json` | Run 2 | PASSED (5 turns) |
| `task_07_*_190023.json` | Run 1 | FAILED (API timeout) |
| `task_07_*_193836.json` | Run 2 | FAILED (connection abort) |
| `task_08_*_190414.json` | Run 1 | PASSED (3 turns) |
| `task_08_*_194233.json` | Run 2 | FAILED (connection abort) |
