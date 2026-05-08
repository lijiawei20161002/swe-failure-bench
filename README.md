# SWE Failure Bench

A single-task benchmark targeting a confirmed capability gap in Kimi 2.6 (`kimi-for-coding`): the async generator finalization contract when using manual `__anext__()` iteration.

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
    retry_stream/           ← active seed (stream.py + tests/)
  trajectories/             ← JSON trajectory files from all eval runs
  eval_kimi.py              ← eval harness
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