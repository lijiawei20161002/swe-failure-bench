# SWE Failure Bench

Eight realistic software-engineering tasks designed to stress-test LLMs on production Python bug-fixing. Each task is based on real production patterns and has multi-stage bugs that require deep language/library understanding to fix correctly.

## Target

Pass rate **< 20%** on Kimi 2.6 (or similar capable models).

## Task Overview

| # | Task | Core Challenge | Bug Count |
|---|------|---------------|-----------|
| 1 | `async_worker_pool` | asyncio cancellation propagation + exception collection in context manager | 4 |
| 2 | `connection_pool` | threading.Condition race condition + close() notification + double-release guard | 3 |
| 3 | `mini_jsonschema` | `additionalProperties` enforcement + `$ref` threading + `oneOf` exact-match semantics | 3 |
| 4 | `tokenizer` | string escape processing + raw strings + triple-quoted multi-line strings | 3 |
| 5 | `lfu_cache` | O(1) LFU with correct `_min_freq` tracking + LRU tie-breaking within buckets | 3 |
| 6 | `query_builder` | SQL clause ordering + parameter ordering with JOINs + OFFSET-without-LIMIT guard | 3 |
| 7 | `event_emitter` | dot-aware glob matching + per-handler error isolation + WeakMethod for bound methods | 3 |
| 8 | `resp_parser` | CRLF consumption after bulk string + position threading in arrays + streaming/pipelining | 3 |

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
