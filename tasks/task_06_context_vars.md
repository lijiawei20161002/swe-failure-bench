# Task: Fix Request-Scoped State with contextvars

## User Persona

- **High-level goals:** Building async web server middleware that attaches request-scoped data (user_id, trace_id) to asyncio Tasks using Python's `contextvars`.
- **Familiarity with tools:** Knows asyncio, has used ContextVar before. Hasn't needed `run_in_fresh_context()` before and is surprised it leaks state.
- **Communication style:** Describes the isolation failure: "The test `test_fresh_context_does_not_inherit_parent_vars` fails — the 'fresh' context still sees the parent's user_id."
- **Patience style:** Patient. Will explain the test carefully if asked.
- **Hint policy:** Will mention "contextvars.copy_context()" if asked. Will not explain how to run in an empty context.

## Context

Implementation: `ctx_state.py`. Tests: `tests/test_ctx.py`.

```bash
cd /workspace && pip install pytest pytest-asyncio --quiet && pytest tests/ -x -q 2>&1 | tail -30
```

## Milestones

### Milestone 1: Fix `run_in_fresh_context()`

**Initial Prompt:**

> "The `run_in_fresh_context()` function is supposed to run a coroutine in a completely isolated context — no inherited state from the caller. But the tests `test_fresh_context_does_not_inherit_parent_vars` and `test_depth_counter_increments_independently` fail because the 'fresh' context leaks the parent's variables. Fix `run_in_fresh_context()` in `ctx_state.py`."

**Planned Interactions:**

- Clarification answers:
  - If agent asks what "fresh context" means: "A context where all ContextVars return their defaults, as if no values had been set. It must not inherit any values from the calling context."
  - If agent asks about `copy_context()`: "`copy_context()` copies the CURRENT context — it still inherits values. You need to start with an empty context."
- Corrections and hints:
  - If agent uses `contextvars.copy_context().run(...)`: "That copies the current context — values still leak. Use `contextvars.Context()` to create a blank context, then call its `.run()` method."
  - If agent wraps in run_in_executor: "For async coroutines in a fresh context, the cleanest approach: create a `contextvars.Context()` object and use `ctx.run(asyncio.run, coro)` or run the coroutine in the context's `.run()` synchronously. For asyncio, `loop.create_task(coro, context=ctx)` accepts a context parameter."

**Completion Criteria:**

`pytest tests/ -x -q` passes all tests.
