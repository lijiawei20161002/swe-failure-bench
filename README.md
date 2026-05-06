# SWE Failure Bench

Six Python bug-fixing tasks targeting the failure modes of Kimi 2.6 (kimi-for-coding).

Tasks were selected/designed by empirical elimination across multiple eval runs. Everything Kimi solved reliably was removed. The remaining tasks combine confirmed failures (02, 03, 08) with new multi-file engineering bugs (07, 09, 10) that require tracing through 3–4 files to understand.

## Benchmark Goal

**Target pass rate: < 20%** on `kimi-for-coding` (or similar frontier coding models).

## Task Overview

| # | Seed file(s) | Core challenge | Design intent |
|---|-------------|---------------|---------------|
| 02 | `task_02_tokenizer/tokenizer.py` | Regex state machine: raw strings, triple-quoted strings, escape sequences | Reasoning chain too long → API abort |
| 03 | `task_03_async_generator/pipeline.py` | Async generator `aclose()` protocol — upstream stages never finalized | Test shows "finalizers not running"; `aclose()` is not deducible from the code |
| 07 | `task_07_saga/orchestrator.py` + `booking.py` + `saga.py` | Saga compensations run in forward order instead of reverse — breaks dependent rollback | 3-file system; `booking.py` documents the dependency but you must read all 3 files to connect the dots |
| 08 | `task_08_gc_cycles/ref_graph.py` | CPython GC tricolor: inverted `gc_refs` subtraction + finalizer leak | Test shows objects not collected; inverted direction looks plausible in both directions |
| 09 | `task_09_query_plan/schema.py` + `planner.py` + `executor.py` + `database.py` | `schema._column_cache` not invalidated after `alter_table()` — planner's cache is correct; bug is in schema | 4-file system; `planner.py` correctly keys on schema version, `schema.py` silently returns stale column list |
| 10 | `task_10_pubsub/broker.py` + `state.py` + `replica.py` | `subscribe_from_snapshot()` is not atomic — events between snapshot and offset capture are silently missed | Classic distributed systems race; invisible without understanding the snapshot/subscribe protocol |

## Running the Eval

```bash
export KIMI_API_KEY=sk-...
python3 eval_kimi.py                      # all 6 tasks
python3 eval_kimi.py --task task_07_saga
python3 eval_kimi.py --max-turns 30
python3 eval_kimi.py --runs 5
```

## Directory Layout

```
swe-failure-bench/
  seeds/
    task_02_tokenizer/
    task_03_async_generator/
    task_07_saga/
    task_08_gc_cycles/
    task_09_query_plan/
    task_10_pubsub/
  tasks/                    ← task descriptions
  trajectories/             ← JSON trajectory files
  eval_kimi.py              ← eval harness
  FINDINGS.md               ← full analysis
```

## Verifying Seeds Fail

```bash
for d in seeds/task_*/; do
  echo -n "$d: "
  (cd $d && python3 -m pytest tests/ -q 2>&1 | tail -1)
done
```

## Empirical Results So Far

### Confirmed failures (previously tested)

| Task | 5-run pass rate | Failure mode |
|------|----------------|--------------|
| 02 tokenizer | 0/5 (0%) | Always API abort — reasoning chain too long |
| 03 async_generator | 0/5 (0%) this run; 2/5 (40%) earlier | Exploration loop / failed writes; never discovers `aclose()` |
| 08 gc_cycles | 2/5 (40%) | Solves when API stable; aborts otherwise |

### Trivially solved — removed

| Task | Pass rate | Why removed |
|------|-----------|-------------|
| lsm_store | 5/5 (100%) | Kimi reads file, spots cache not invalidated, fixes in 2–3 turns |
| wal_recovery | 5/5 (100%) | Kimi spots `>=` vs `>` off-by-one immediately |
| connpool | 5/5 (100%) | Kimi spots missing `rollback()` in checkin path immediately |
| exc_info_leak | 5/5 (100%) | Kimi knows `sys.exc_info()[2]` traceback retention |
| frame_codec | 5/5 (100%) | Kimi spots byte-order mismatch across 2 files |
| generator_stop | 5/5 (100%) | Kimi knows PEP 479 StopIteration behavior |
| weakref_callback | 5/5 (100%) | Kimi knows bound methods are ephemeral in WeakValueDictionary |
| context_vars | 5/5 (100%) | Kimi knows `contextvars.Context()` isolation pattern |
| raft_log | 5/5 (100%) | Kimi knows Raft AppendEntries spec |
| btree | 5/5 (100%) | Kimi knows CLRS B-tree split algorithm |
| async_worker_pool | 4/5 (80%) | Kimi knows asyncio cancellation patterns |

### New tasks (07, 09, 10) — not yet tested
