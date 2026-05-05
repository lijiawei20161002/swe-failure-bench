# SWE Failure Bench

Eight Python bug-fixing tasks designed to expose the limits of Kimi 2.6 (kimi-for-coding).
Tasks 01–02 were carried over from an initial 14-task batch after empirical eval showed
they reliably caused failures. Tasks 03–08 were designed from scratch based on those findings.

## Benchmark Goal

**Target pass rate: < 20%** on `kimi-for-coding` (or similar frontier coding models).

**Observed pass rate: 52.5%** (21/40 over 5 runs) — see `FINDINGS.md` for full analysis.

## Task Overview

| # | Seed file | Core challenge | Kimi result |
|---|-----------|---------------|-------------|
| 01 | `async_worker_pool/worker_pool.py` | asyncio cancellation propagation + PoolShutdownError + graceful shutdown | ✓ PASSED (3 turns) |
| 02 | `tokenizer/tokenizer.py` | Regex state machine: raw strings + triple-quoted + escape sequences | ✗ FAILED (API abort) |
| 03 | `async_generator/pipeline.py` | Async generator `aclose()` protocol — upstream stages never finalized | ✗ FAILED (30 turns, no fix written) |
| 04 | `btree/btree.py` | B-tree split off-by-one (t vs t-1) + live cursor reflecting deletions | ✓ PASSED (2 turns) |
| 05 | `regex_engine/regex_engine.py` | NFA construction: unhashable State + broken ε-closure + range classes | ✗ FAILED (API abort) |
| 06 | `context_vars/ctx_state.py` | `contextvars.Context()` fresh isolation vs `copy_context()` | ✓ PASSED (4 turns) |
| 07 | `raft_log/raft_log.py` | Raft AppendEntries: commit-on-reject + wrong truncation slice offset | ✓ PASSED (3 turns) |
| 08 | `gc_cycles/ref_graph.py` | CPython GC tricolor: inverted gc_refs subtraction + finalizer leak | ✗ FAILED (4 turns, no fix written) |

## Running the Eval

```bash
export KIMI_API_KEY=sk-...
python3 eval_kimi.py                      # all 8 tasks
python3 eval_kimi.py --task task_03_async_generator
python3 eval_kimi.py --max-turns 30
```

The eval script requires `requests` and `pytest` / `pytest-asyncio`.

## Directory Layout

```
swe-failure-bench/
  seeds/
    task_01_async_worker_pool/    ← buggy implementation + tests
    task_02_tokenizer/
    task_03_async_generator/
    task_04_btree/
    task_05_regex_engine/
    task_06_context_vars/
    task_07_raft_log/
    task_08_gc_cycles/
  tasks/                          ← synthetic-user task descriptions (opencode format)
    task_01_async_worker_pool.md
    ...
  trajectories/                   ← JSON trajectory files from eval runs
  eval_kimi.py                    ← eval harness
  FINDINGS.md                     ← full analysis and results
```

## Test Commands

```bash
# Verify each seed fails before running the eval
for d in seeds/task_*/; do
  echo -n "$d: "
  (cd $d && python3 -m pytest tests/ -q 2>&1 | tail -1)
done
```
