"""
Request-scoped state using Python's contextvars.

In an async web server, each request handler runs in its own asyncio Task.
We want request-scoped state (user_id, trace_id, etc.) that:
  1. Propagates into child tasks created within the request (copy-on-write)
  2. Does NOT leak from one request to another (isolation)
  3. Supports middleware that set values BEFORE calling the handler

This is exactly what Python's `contextvars.ContextVar` + `copy_context()`
is designed for, but using it correctly is subtle.

Based on patterns from: Starlette, FastAPI, aiohttp middleware chains.

Public API:
    state = RequestState()

    # In middleware:
    token = state.user_id.set("alice")

    # In handler:
    uid = state.user_id.get()   # "alice"

    # In child task spawned from handler:
    uid = state.user_id.get()   # should also be "alice" (inherited)

    # In different request (different task):
    uid = state.user_id.get()   # should be default, not "alice"
"""

from __future__ import annotations

import asyncio
import contextvars
from typing import Any, Optional


class RequestState:
    """Per-request state backed by ContextVars."""

    user_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
        "user_id", default=None
    )
    trace_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
        "trace_id", default=None
    )
    request_depth: contextvars.ContextVar[int] = contextvars.ContextVar(
        "request_depth", default=0
    )


state = RequestState()


async def simulate_request(user: str, trace: str, handler) -> Any:
    """
    Simulates a middleware setting request-scoped context, then calling handler.

    BUG A: We set the ContextVar directly but then create the handler task
    without copying the current context. asyncio.create_task() copies the
    context automatically IF called from within the context where the vars
    are set — but here we create the task AFTER setting, which works.

    However, the real bug is in simulate_request_broken below.
    """
    token_u = state.user_id.set(user)
    token_t = state.trace_id.set(trace)
    try:
        return await handler()
    finally:
        state.user_id.reset(token_u)
        state.trace_id.reset(token_t)


async def simulate_request_broken(user: str, trace: str, handler) -> Any:
    """
    BUG A: Creates the handler task BEFORE setting the context variables,
    then tries to set them — but the task's context copy was already made
    at create_task() time, so the variables are NOT set in the task's context.

    The fix: set variables BEFORE creating the task, OR use
    contextvars.copy_context().run(handler) instead of create_task().
    """
    # BUG A: task is created before context vars are set
    task = asyncio.create_task(handler())
    state.user_id.set(user)    # BUG A: too late — task's context was copied before this
    state.trace_id.set(trace)  # BUG A: same
    return await task


async def spawn_child_task(coro) -> Any:
    """
    Spawn a child task that inherits the current context.

    BUG B: We wrap the coroutine in asyncio.create_task() which DOES
    inherit the current context snapshot automatically. However, if the
    child modifies a ContextVar, those changes do NOT propagate back to
    the parent — contextvars are copy-on-write. This is correct behavior,
    but our tests verify the child CAN read the parent's values.

    The bug here is that we use `asyncio.ensure_future` which in some
    Python versions does NOT copy the context, making child reads fail.
    """
    # BUG B: ensure_future doesn't always copy context in Python < 3.7
    # In Python 3.7+ create_task copies context; ensure_future may not.
    # Use create_task for guaranteed context inheritance.
    return await asyncio.ensure_future(coro)   # BUG B: should use create_task


async def run_in_fresh_context(coro) -> Any:
    """
    Run *coro* in a completely fresh context (no inherited state).
    This is used to isolate one request from another.

    BUG C: We just create a normal task, which inherits the current
    context. For true isolation, we need to run in an empty context:
        ctx = contextvars.Context()
        return await asyncio.get_event_loop().run_in_executor(
            None, ctx.run, asyncio.run, coro
        )
    or use copy_context() and manually clear vars.

    Current implementation leaks context from caller into the "fresh" context.
    """
    # BUG C: inherits caller's context instead of starting fresh
    return await asyncio.create_task(coro)
