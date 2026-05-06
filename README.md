# SWE Failure Bench

Three Python bug-fixing tasks that reliably expose the limits of Kimi 2.6 (kimi-for-coding).

Tasks were selected by empirical elimination: 14 tasks were evaluated over multiple runs; tasks Kimi solved reliably were discarded. These 3 are what remain after all easy tasks were removed.

## Benchmark Goal

**Target pass rate: < 20%** on `kimi-for-coding` (or similar frontier coding models).

**Observed pass rate: ~33–57%** depending on API reliability (see `FINDINGS.md`).

## Task Overview

| # | Seed file | Core challenge | Kimi failure mode |
|---|-----------|---------------|-------------------|
| 02 | `task_02_tokenizer/tokenizer.py` | Regex state machine: raw strings + triple-quoted + escape sequences | API connection abort — reasoning chain exceeds timeout |
| 03 | `task_03_async_generator/pipeline.py` | Async generator `aclose()` protocol — upstream stages never finalized | Exploration loop — 30 turns of `pytest` without discovering `aclose()` |
| 08 | `task_08_gc_cycles/ref_graph.py` | CPython GC tricolor: inverted `gc_refs` subtraction + finalizer leak | API abort or fails to identify the inverted direction |

## Running the Eval

```bash
export KIMI_API_KEY=sk-...
python3 eval_kimi.py                      # all 3 tasks
python3 eval_kimi.py --task task_03_async_generator
python3 eval_kimi.py --max-turns 30
python3 eval_kimi.py --runs 5            # 5 independent runs per task
```

The eval script requires `requests` and `pytest` / `pytest-asyncio`.

## Directory Layout

```
swe-failure-bench/
  seeds/
    task_02_tokenizer/        ← buggy implementation + tests
    task_03_async_generator/
    task_08_gc_cycles/
  tasks/                      ← synthetic-user task descriptions
    task_02_tokenizer.md
    task_03_async_generator.md
    task_08_gc_cycles.md
  trajectories/               ← JSON trajectory files from eval runs
  eval_kimi.py                ← eval harness
  FINDINGS.md                 ← full analysis and results
```

## Verifying Seeds Fail Before Eval

```bash
for d in seeds/task_*/; do
  echo -n "$d: "
  (cd $d && python3 -m pytest tests/ -q 2>&1 | tail -1)
done
```

Expected output: each seed has failing tests.

## Why These Tasks Are Hard

Both task_03 and task_08 share the same failure pattern:

**Test output shows a symptom that doesn't implicate the root cause.**

| Task | What the tests show | What Kimi needs to know |
|------|---------------------|------------------------|
| tokenizer | Wrong token types / values | 10+ overlapping regex rules for raw strings, triple-quoted strings, and escape sequences — too many to reason through simultaneously |
| async_generator | Finalizers not running | `aclose()` must be explicitly awaited on each generator in the chain (PEP 525) — Python does not auto-close upstream generators |
| gc_cycles | Objects not collected | CPython tricolor GC: `gc_refs` subtraction must decrement the *target*'s count, not the *holder*'s — the direction is counterintuitive |

## What Kimi Solves Easily (Removed)

The following were removed because Kimi solved them in 2–3 turns, demonstrating they are well-represented in its training data:

| Task | What Kimi knew |
|------|---------------|
| exc_info_leak | `sys.exc_info()[2]` traceback retains frame locals |
| frame_codec | struct byte-order `<I` vs `>I` mismatch across files |
| generator_stop | PEP 479: `StopIteration` inside generator → `RuntimeError` |
| weakref_callback | Bound methods are ephemeral; `WeakValueDictionary` drops them |
| async_worker_pool | asyncio cancellation + `PoolShutdownError` pattern |
| btree | B-tree CLRS split off-by-one |
| regex_engine | NFA Thompson construction bugs |
| context_vars | `contextvars.Context()` fresh isolation pattern |
| raft_log | Raft `append_entries` spec violations |
