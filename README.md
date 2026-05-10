# SWE Failure Bench

A benchmark targeting confirmed capability gaps in Kimi 2.6 (`kimi-for-coding`): execution-semantic bugs that defeat local-repair strategies.

## Tasks

| Seed | Category | Core challenge | Pass rate |
|------|----------|---------------|-----------|
| `seeds/retry_stream` | async | `StreamProcessor` uses manual `__anext__()` instead of `async for` — source generator is never `aclose()`'d on exception or cancellation | **0/8 (0%)** |
| `seeds/thread_counter` | threading | `KeyCounter.increment_many()` calls `increment()` while holding `threading.Lock` — self-deadlock requires `RLock`; tests detect deadlock via 0.5 s timeout | removed — Kimi solved in 3 turns |
| `seeds/proc_counter` | multiprocessing | `counter.value += 1` across worker processes is a non-atomic read-modify-write; `multiprocessing.Value`'s built-in lock is never acquired; lost increments manifest as wrong totals | removed — Kimi solved in 2 turns |

## Why these tasks

All three bugs share the same structure:
- The fix IS known to the model (`aclose()`, `RLock`, `get_lock()`)
- The model does NOT recognise the pattern as requiring the fix
- The error output misdirects toward a local/surface symptom

**`retry_stream`**: Kimi knows `async for` triggers cleanup but does not connect manual `__anext__()` loops to needing `await it.aclose()`. Kimi spent all 30 turns experimenting with `StopIteration` semantics in `/tmp/` and never wrote to `stream.py`.

**`thread_counter`**: Kimi knows `RLock` is reentrant but the deadlock error `"increment_many() did not complete within 0.5 s"` looks like a performance/timeout issue. Five basic `increment()` tests pass — the model sees a method that *mostly works* and looks for a logic fix in `increment_many()`, not a primitive swap in `__init__`.

**`proc_counter`**: Kimi knows `multiprocessing.Value` has a lock but `counter.value += 1` looks like ordinary arithmetic. The failure `"Expected 20000, got 11347"` looks like an off-by-one or wrong formula — exactly the kind of local error that transformer-based local repair fixes well, but in the wrong direction.

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

## How the Eval Works

`eval_kimi.py` discovers tasks by scanning `seeds/` for subdirectories that contain a `tests/` folder. For each task it:

1. Reads the implementation file(s) and test file(s) from the seed directory
2. Pastes them verbatim into the opening user message with a generic instruction: *"fix all bugs so `python3 -m pytest tests/ -v` exits with return code 0"*
3. Runs Kimi in a tool-use loop (`read_file`, `write_file`, `run_bash`) for up to `--max-turns` turns
4. After each `write_file` call, runs the test suite and records pass/fail

No task description files are used — the prompt is built entirely from the seed source.

## Directory Layout

```
swe-failure-bench/
  seeds/
    retry_stream/           ← async generator finalization (stream.py + tests/)
    thread_counter/         ← threading Lock vs RLock deadlock (counter.py + tests/)
    proc_counter/           ← multiprocessing.Value race condition (counter.py + tests/)
  trajectories/             ← JSON trajectory files from all eval runs
  eval_kimi.py              ← eval harness
```

## Verifying the Seeds Fail

```bash
cd seeds/retry_stream   && python3 -m pytest tests/ -x -q 2>&1 | tail -5
cd seeds/thread_counter && python3 -m pytest tests/ -q   2>&1 | tail -5
cd seeds/proc_counter   && python3 -m pytest tests/ -q   2>&1 | tail -5
```

## Results

### `retry_stream` — 0/8 (0%)

| Run set | Writes | Failure mode |
|---------|--------|-------------|
| Initial 5 runs (2026-05-07) | 0 | All `run_bash`; fixated on `StopIteration` semantics in `/tmp/`, never opened `stream.py` |
| Rerun run 1 (2026-05-10) | 0 | Same pattern |
| Rerun run 2 (2026-05-10) | **1** | Turns 1–17 bash → turn 18 `read_file` → turn 19 `write_file` (correct `aclose()` fix) → 1 test still failing; turns 20–30 bash failing to crack PEP 479 `StopIteration`→`RuntimeError` |
| Rerun run 3 (2026-05-10) | 0 | All `run_bash`, 0 writes |

**Run 2 is notable**: Kimi did find the correct fix (`try/finally: await it.aclose()` in both `process()` and `process_async()`). The remaining failure is `test_large_source_finalizes_on_early_abort`, where the transform raises `StopIteration("early abort")`. In Python 3.7+, `StopIteration` exiting an `async def` frame becomes `RuntimeError: coroutine raised StopIteration` (PEP 479), so `pytest.raises(StopIteration)` can never catch it without a creative workaround. Kimi spent its final 11 turns unable to bridge this.

**What makes `retry_stream` hard**: two compounding gaps — (1) recognising that manual `__anext__()` loops need `await it.aclose()` (no canonical name for this pattern), and (2) the PEP 479 `StopIteration`→`RuntimeError` semantics in the one edge-case test.

### Removed seeds

`thread_counter` (Lock→RLock deadlock) and `proc_counter` (`multiprocessing.Value` race) were solved by Kimi in 3 and 2 turns — both map to canonical named patterns in training data and are poor benchmarks.