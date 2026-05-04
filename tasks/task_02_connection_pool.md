# Task: Fix Thread-Safe Connection Pool

## User Persona

- **High-level goals:** Running a Python web service that uses a custom connection pool. Under moderate load (~50 concurrent requests) the pool sometimes hands out more connections than `max_size` allows, and threads waiting for connections hang forever after calling `pool.close()`.
- **Familiarity with tools:** Mid-to-senior Python developer. Understands threading basics (Lock, Thread) but has not worked with `threading.Condition` in depth. Knows what a race condition is but can't always spot one in code.
- **Communication style:** Describes symptoms precisely ("30 threads calling acquire() and I count 12 open DB connections but max_size=10"). Pastes error output.
- **Patience style:** Patient but will escalate to "this is a production bug, I need it fixed" after 2 failed attempts.
- **Hint policy:** Will share thread dumps if asked. Will not suggest which lock to use.

## Context

Implementation: `connection_pool.py`. Tests: `tests/test_connection_pool.py`.

```bash
cd /workspace && pip install pytest --quiet && pytest tests/ -x -q 2>&1 | tail -30
```

## Milestones

### Milestone 1: Fix Pool Size Race Condition

**Initial Prompt:**

> "I have a connection pool that's supposed to cap at `max_size` connections. Under load I see more connections than the cap. Look at `connection_pool.py` — the test `test_pool_size_never_exceeds_max` in `tests/test_connection_pool.py` reproduces it. Can you find and fix the race condition?"

**Planned Interactions:**

- Clarification answers:
  - If agent asks what database this pools: "Doesn't matter — the `factory` callable creates the connection object. Look at FakeConn in the tests."
  - If agent asks if it can rewrite entirely: "You can restructure the class, but keep the same public API: acquire(), release(), close(), size, idle_count."
- Corrections and hints:
  - If agent adds a lock but the race still exists: "The test still fails — try running it 5 times; it fails intermittently. The issue is that the check and the create aren't atomic."
  - If agent uses `with self._lock` but creates connection inside: "You're acquiring the lock but the factory call is inside — what happens if two threads both pass the `total < max_size` check before either creates?"

**Completion Criteria:**

`pytest tests/test_connection_pool.py::TestBasic -x -q` passes all tests including `test_pool_size_never_exceeds_max`.

---

### Milestone 2: Fix close() Hanging Blocked Acquirers

**Initial Prompt:**

> "Pool size is fixed, thanks. New issue: when I call `pool.close()` from a signal handler, threads that are blocked inside `acquire()` hang forever. The test `test_close_unblocks_waiting_acquirers` shows this. Fix it."

**Planned Interactions:**

- Corrections and hints:
  - If agent adds `notify_all()` inside close() but forgets to set `_closed`: "The threads wake up but don't raise PoolClosedError — they just loop and block again."
  - If close() notifies but threads still hang: "Make sure you set `_closed = True` before notifying, so the threads see it when they re-check."

**Completion Criteria:**

`pytest tests/test_connection_pool.py::TestClose -x -q` passes all 3 tests.

---

### Milestone 3: Guard Against Double-Release

**Initial Prompt:**

> "One more thing — releasing a connection twice (or releasing a foreign object) corrupts the pool's internal state. Add validation so those cases raise a ValueError. The test class `TestDoubleRelease` covers this."

**Planned Interactions:**

- Clarification answers:
  - If agent asks what to raise: "ValueError or AssertionError is fine — the test accepts either."
- Corrections and hints:
  - If agent only tracks by object identity: "Make sure releasing a connection that was already returned also raises, not just releasing a foreign object."

**Completion Criteria:**

`pytest tests/ -x -q` passes all tests.
