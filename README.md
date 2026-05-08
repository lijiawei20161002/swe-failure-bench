# SWE Failure Bench

A single-task benchmark targeting a confirmed capability gap in Kimi 2.6 (`kimi-for-coding`): the async generator finalization contract when using manual `__anext__()` iteration.

Tasks were selected by empirical elimination across multiple eval runs (May 4–8, 2026). Everything Kimi solved reliably was removed. See `FINDINGS.md` for the full elimination history.

## Active Task

| Seed | Core challenge | Pass rate (5 runs) |
|------|---------------|-------------------|
| `seeds/retry_stream/stream.py` | `StreamProcessor` uses manual `__anext__()` instead of `async for` — source generator is never `aclose()`'d on exception or cancellation | 0/5 (0%) |

**Why this task:** Kimi knows that `async for` triggers cleanup but does not recognise the manual `__anext__()` pattern as requiring explicit `await source.aclose()` in a `finally` block. This is a genuine capability gap, not a trick — the fix is straightforward once you know it, but Kimi never writes it. 0 writes across all 7 observed failure runs.

The two distinct failing tests (vary by run):
- `test_source_finalizes_on_task_cancellation` — source not finalized when `asyncio.CancelledError` propagates through the manual loop
- `test_large_source_finalizes_on_early_abort` — source not finalized when the transform raises `StopIteration`

## Running the Eval

```bash
export KIMI_API_KEY=sk-...
python3 eval_kimi.py                # retry_stream, 1 run
python3 eval_kimi.py --runs 5       # 5 runs
python3 eval_kimi.py --max-turns 40 # more turns (default 30)
```

## Directory Layout

```
swe-failure-bench/
  seeds/
    retry_stream/           ← active seed (stream.py + tests/)
  tasks/                    ← task descriptions (tokenizer, gc_cycles kept as archive)
  trajectories/             ← JSON trajectory files from all eval runs
  eval_kimi.py              ← eval harness
  FINDINGS.md               ← full elimination history and failure analysis
```

## Verifying the Seed Fails

```bash
cd seeds/retry_stream && python3 -m pytest tests/ -x -q 2>&1 | tail -5
```

## Results Summary

### Active task

| Task | 5-run pass rate | Failure mode |
|------|----------------|--------------|
| retry_stream | 0/5 (0%) | Genuine gap — never recognises `__anext__()` loop needs explicit `aclose()` |

### Retired tasks

| Task | Reason retired |
|------|---------------|
| 02 tokenizer | API abort on every run — infrastructure failure, not capability |
| 03 async_generator | Mode C failure: Kimi adds `aclose()` but iterates forward instead of `reversed()` — ordering trick, not genuine gap |
| 04 concurrent_pipeline | Solved 1/1 — too easy |
| 06 stream_multiplexer | Solved 1/1 — too easy |
| 07 saga | Not yet tested |
| 08 gc_cycles | API-unreliable; 2/5 when stable — not a clean 0% |
| 09 query_plan | Not yet tested |
| 10 pubsub | Not yet tested |
| exc_info_leak | 5/5 — Kimi knows `sys.exc_info()` traceback retention |
| frame_codec | 5/5 — Kimi spots byte-order mismatch |
| generator_stop | 5/5 — Kimi knows PEP 479 |
| weakref_callback | 5/5 — Kimi knows bound methods are ephemeral in WeakValueDictionary |
| context_vars | 5/5 — Kimi knows `contextvars.Context()` isolation |
| raft_log | 5/5 — Kimi knows Raft AppendEntries spec |
| btree | 5/5 — Kimi knows CLRS B-tree split |
| async_worker_pool | 4/5 — Kimi knows asyncio cancellation patterns |
