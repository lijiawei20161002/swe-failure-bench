# SWE Failure Bench

Fourteen realistic software-engineering tasks designed to stress-test LLMs on production Python bug-fixing. Tasks 1–8 were the initial batch (observed 50% pass rate vs Kimi 2.6). Tasks 9–14 are the hardened batch targeting <20% pass rate, based on findings from the initial evaluation.

## Target

Pass rate **< 20%** on Kimi 2.6 (or similar capable models).

## Task Overview

### Initial Batch (Tasks 1–8) — observed ~50% pass rate vs Kimi 2.6

| # | Task | Core Challenge | Kimi result |
|---|------|---------------|-----------|
| 1 | `async_worker_pool` | asyncio cancellation propagation + exception re-raise | PASSED |
| 2 | `connection_pool` | threading.Condition race + notify_all + double-release | PASSED |
| 3 | `mini_jsonschema` | oneOf exact-match + $ref threading + additionalProperties | FAILED (API timeout) |
| 4 | `tokenizer` | raw strings + triple-quoted + escape sequences | FAILED (API timeout) |
| 5 | `lfu_cache` | O(1) LFU _min_freq tracking + LRU tie-breaking | PASSED |
| 6 | `query_builder` | SQL clause ordering + JOIN param order | PASSED |
| 7 | `event_emitter` | dot-aware glob + WeakMethod + error isolation | FAILED (API timeout) |
| 8 | `resp_parser` | CRLF consumption + array position threading | FAILED (API timeout) |

### Hardened Batch (Tasks 9–14) — designed for <20% pass rate

| # | Task | Why harder | Bug Count |
|---|------|-----------|-----------|
| 9 | `sliding_window` | Injectable-clock bugs; boundary semantics not obvious from error message | 2 |
| 10 | `expr_evaluator` | **Multi-file** (lexer+parser+evaluator); 3 independent bugs across files | 3 |
| 11 | `weighted_cache` | Two interacting bugs: eviction condition AND size-on-update both wrong | 2 |
| 12 | `rope` | Off-by-one in recursive split; boundary case in internal nodes; character loss | 2 |
| 13 | `json_rpc` | **Multi-file** (protocol+dispatcher+client); swapped error codes + notification semantics + id-based matching | 3 |
| 14 | `pkg_resolver` | `>=`/`<=` boundary bug (wrong output, not exception) + missing transitive resolution | 2 |

## Why These Trip Up LLMs

Each task has been designed so that the **obvious first fix is insufficient** and multiple interacting bugs must all be resolved:

- **Task 1**: Fixing exception re-raise is obvious; cancelling siblings and collecting multiple exceptions requires restructuring the internal task set management.
- **Task 3**: Adding `additionalProperties` check is straightforward; threading `_defs` through recursive property validation and making `oneOf` count *all* matches (not stop early) are separate, non-obvious fixes.
- **Task 5**: Changing `_evict()` to use `_min_freq` fixes one thing; keeping `_min_freq` correct after `put()` and `_increment()` are separate invariants.
- **Task 7**: `fnmatch` replacement for dot-aware globs is known; `WeakMethod` for bound methods (vs `weakref.ref` which immediately dies) is a common Python trap.
- **Task 8**: The CRLF-after-bulk-string bug is well-known; the array position bug (`pos` not threaded between elements) is a separate indexing error.

## Structure

```
swe-failure-bench/
  tasks/           ← task description .md files (synthetic user format)
  seeds/
    task_01_async_worker_pool/
      worker_pool.py       ← buggy implementation
      tests/
        test_worker_pool.py
    task_02_connection_pool/
      ...
    ...
```

## Running Tasks with OpenCode + Synthetic User

Copy the `opencode-setup-offline-exp 10` scripts and config, then:

```bash
# Seed the workspace
cp -r seeds/task_01_async_worker_pool/* /path/to/opencode-setup/seed/

# Run with Kimi
cd /path/to/opencode-setup
./scripts/run_task.sh model_A ../swe-failure-bench/tasks/task_01_async_worker_pool.md
```

Or use the Kimi eval wrapper:

```bash
python3 run_kimi_eval.py --task tasks/task_01_async_worker_pool.md
```

## Scoring

A task is **passed** only when the full test suite runs clean:
```bash
cd /workspace && pytest tests/ -x -q
```

Partial milestone completion does not count as a pass.

## Test Commands Per Task

```bash
# Task 1
pip install pytest pytest-asyncio && pytest tests/ -x -q

# Tasks 2–8
pip install pytest && pytest tests/ -x -q
```
