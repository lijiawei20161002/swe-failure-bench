# Task: Fix AsyncIO Worker Pool

## User Persona

- **High-level goals:** Debug and fix a production async worker pool used in a web service backend. The pool manages background jobs (sending emails, processing uploads, etc.).
- **Familiarity with tools:** Senior backend engineer, comfortable with Python asyncio fundamentals (tasks, futures, gather) but hasn't dug into cancellation propagation semantics or TaskGroup internals.
- **Opinions on patterns:** Prefers explicit over magic; wants the pool to behave predictably under failure.
- **Communication style:** Direct and technical. Provides stack traces. Expects working code, not explanations of why things are hard.
- **Patience style:** Will try the fix once; if tests still fail, points to which test failed and asks what's wrong.
- **Hint policy:** Will paste the failing test output on second failure. Will not suggest implementation strategies.

## Context

The starting codebase is in the `workspace/` directory. The implementation is in `worker_pool.py`. Tests are in `tests/test_worker_pool.py`. Run tests with:

```bash
cd /workspace && pip install pytest pytest-asyncio --quiet && pytest tests/ -x -q 2>&1 | tail -30
```

## Milestones

### Milestone 1: Fix Exception Propagation and Sibling Cancellation

**Initial Prompt:**

> "Hey, I have an async worker pool that's misbehaving in production. When one worker throws an exception, the other workers keep running indefinitely — they should be cancelled. Also when I use it as a context manager, the exception from the worker is swallowed and my outer code never sees it. The tests in `tests/test_worker_pool.py` cover these cases. Can you look at `worker_pool.py` and fix it?"

**Planned Interactions:**

- Clarification answers:
  - If agent asks what async library to use: "Just stdlib asyncio, no anyio or trio"
  - If agent asks about Python version: "Python 3.11+"
- Corrections and hints:
  - If agent's fix doesn't pass `test_exception_cancels_siblings`: "The test still fails — siblings aren't being cancelled. Maybe look at how the exception is caught in `_run`?"
  - If agent re-raises but doesn't cancel siblings: "Cancellation still isn't happening. The pool needs to know when any worker fails and cancel the rest."
  - If agent uses `asyncio.TaskGroup` directly: "That's fine if it fixes the semantics, but make sure the existing public API (submit, shutdown) still works."

**Completion Criteria:**

`pytest tests/test_worker_pool.py::TestExceptionPropagation -x -q` passes all 3 tests.

---

### Milestone 2: Fix Shutdown Semantics and PoolShutdownError

**Initial Prompt:**

> "Great, now the exception tests pass. But `shutdown()` doesn't wait for in-flight tasks when `cancel=False`, and calling `submit()` after shutdown raises a plain `RuntimeError` instead of `PoolShutdownError`. Fix those too."

**Planned Interactions:**

- Clarification answers:
  - If agent asks what PoolShutdownError should inherit from: "It should be a subclass of WorkerPoolError, which is already defined"
- Corrections and hints:
  - If `test_graceful_shutdown_waits_for_inflight` still fails: "The shutdown finishes before the workers do — check how you're awaiting the tasks"
  - If double-shutdown raises: "Calling shutdown twice should be a no-op, not an error"

**Completion Criteria:**

`pytest tests/ -x -q` passes all tests (TestConcurrency, TestExceptionPropagation, TestShutdown).
