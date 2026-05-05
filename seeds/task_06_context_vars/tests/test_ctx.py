"""Tests for context variable propagation. Run: pip install pytest pytest-asyncio && pytest tests/ -x"""
import asyncio
import contextvars
import pytest
from ctx_state import state, simulate_request, simulate_request_broken, spawn_child_task, run_in_fresh_context


# ── basic ContextVar behavior ─────────────────────────────────────────────────

class TestBasicContextVar:
    @pytest.mark.asyncio
    async def test_set_and_get_in_same_context(self):
        token = state.user_id.set("alice")
        try:
            assert state.user_id.get() == "alice"
        finally:
            state.user_id.reset(token)

    @pytest.mark.asyncio
    async def test_default_when_not_set(self):
        assert state.user_id.get() is None

    @pytest.mark.asyncio
    async def test_reset_restores_previous(self):
        token1 = state.user_id.set("alice")
        token2 = state.user_id.set("bob")
        assert state.user_id.get() == "bob"
        state.user_id.reset(token2)
        assert state.user_id.get() == "alice"
        state.user_id.reset(token1)
        assert state.user_id.get() is None


# ── simulate_request: correct version ────────────────────────────────────────

class TestSimulateRequest:
    @pytest.mark.asyncio
    async def test_handler_sees_set_values(self):
        seen = {}

        async def handler():
            seen["user"] = state.user_id.get()
            seen["trace"] = state.trace_id.get()

        await simulate_request("alice", "trace-1", handler)
        assert seen["user"] == "alice"
        assert seen["trace"] == "trace-1"

    @pytest.mark.asyncio
    async def test_context_reset_after_request(self):
        async def handler():
            pass

        await simulate_request("bob", "trace-2", handler)
        # After request completes, values should be restored
        assert state.user_id.get() is None
        assert state.trace_id.get() is None

    @pytest.mark.asyncio
    async def test_two_requests_isolated(self):
        """Two concurrent requests must not see each other's state."""
        results = {}

        async def handler_a():
            await asyncio.sleep(0.05)
            results["a"] = state.user_id.get()

        async def handler_b():
            await asyncio.sleep(0.02)
            results["b"] = state.user_id.get()

        await asyncio.gather(
            simulate_request("alice", "t-a", handler_a),
            simulate_request("bob", "t-b", handler_b),
        )
        assert results["a"] == "alice", f"Request A got user_id={results['a']!r}"
        assert results["b"] == "bob", f"Request B got user_id={results['b']!r}"


# ── BUG A: broken simulate_request ───────────────────────────────────────────

class TestSimulateRequestBroken:
    @pytest.mark.asyncio
    async def test_handler_does_not_see_late_set_values(self):
        """
        When context vars are set AFTER create_task(), the task's context
        copy is already made — it does NOT see the late-set values.

        simulate_request_broken() creates the task before setting the vars,
        so the handler should see None (the default), not the set values.
        """
        seen = {}

        async def handler():
            seen["user"] = state.user_id.get()

        await simulate_request_broken("alice", "trace-X", handler)
        assert seen["user"] is None, (
            f"Handler saw user_id={seen['user']!r} but vars were set AFTER "
            "create_task() — the task's context copy was already made. "
            "BUG A: task created before context var is set."
        )


# ── BUG B: child task context inheritance ────────────────────────────────────

class TestChildTaskInheritance:
    @pytest.mark.asyncio
    async def test_child_inherits_parent_context(self):
        """
        A child task spawned via asyncio.create_task() inherits the parent's
        context snapshot at the time of creation.
        """
        token = state.user_id.set("parent-user")
        try:
            child_saw = {}

            async def child():
                child_saw["user"] = state.user_id.get()

            result = await spawn_child_task(child())
            assert child_saw["user"] == "parent-user", (
                f"Child task saw user_id={child_saw['user']!r} but expected 'parent-user'. "
                "BUG B: ensure_future() may not copy context; use create_task()."
            )
        finally:
            state.user_id.reset(token)

    @pytest.mark.asyncio
    async def test_child_modification_does_not_affect_parent(self):
        """Child setting a ContextVar must not affect the parent (copy-on-write)."""
        token = state.user_id.set("parent")
        try:
            async def child():
                state.user_id.set("child-override")   # should NOT affect parent

            await asyncio.create_task(child())
            assert state.user_id.get() == "parent"
        finally:
            state.user_id.reset(token)

    @pytest.mark.asyncio
    async def test_nested_child_inherits_grandparent_context(self):
        """Transitive inheritance: grandchild sees grandparent's values."""
        token = state.trace_id.set("root-trace")
        try:
            result = {}

            async def grandchild():
                result["trace"] = state.trace_id.get()

            async def child():
                await asyncio.create_task(grandchild())

            await asyncio.create_task(child())
            assert result["trace"] == "root-trace"
        finally:
            state.trace_id.reset(token)


# ── BUG C: fresh context isolation ───────────────────────────────────────────

class TestFreshContext:
    @pytest.mark.asyncio
    async def test_fresh_context_does_not_inherit_parent_vars(self):
        """
        run_in_fresh_context() must run in a blank context — the coroutine
        must NOT see values that were set in the caller's context.
        """
        token = state.user_id.set("should-not-leak")
        try:
            seen = {}

            async def isolated_handler():
                seen["user"] = state.user_id.get()

            await run_in_fresh_context(isolated_handler())
            assert seen["user"] is None, (
                f"Fresh context leaked parent's user_id={seen['user']!r}. "
                "BUG C: run_in_fresh_context() inherits caller's context "
                "instead of starting with a clean slate."
            )
        finally:
            state.user_id.reset(token)

    @pytest.mark.asyncio
    async def test_depth_counter_increments_independently(self):
        """Each request context should have an independent depth counter."""
        token = state.request_depth.set(5)
        try:
            depths = {}

            async def handler():
                depths["inner"] = state.request_depth.get()

            await run_in_fresh_context(handler())
            # Fresh context: depth should be default (0), not 5
            assert depths["inner"] == 0, (
                f"Fresh context got depth={depths['inner']}, expected 0. "
                "Context was not properly isolated."
            )
        finally:
            state.request_depth.reset(token)
