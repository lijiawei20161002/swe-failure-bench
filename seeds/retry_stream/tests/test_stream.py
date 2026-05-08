"""Tests for async stream processor. Run: pip install pytest pytest-asyncio && pytest tests/ -x"""
import asyncio
import pytest
from stream import StreamProcessor, make_source


# ── basic correctness ─────────────────────────────────────────────────────────

class TestBasic:
    @pytest.mark.asyncio
    async def test_applies_transform(self):
        finalized = []
        src = make_source("A", [1, 2, 3], finalized)
        result = await StreamProcessor().process(src, lambda x: x * 2)
        assert result == [2, 4, 6]

    @pytest.mark.asyncio
    async def test_empty_source(self):
        finalized = []
        src = make_source("A", [], finalized)
        result = await StreamProcessor().process(src, lambda x: x)
        assert result == []

    @pytest.mark.asyncio
    async def test_exception_from_fn_propagates(self):
        finalized = []
        src = make_source("A", [1, 2, 3], finalized)

        def bad_fn(x):
            if x == 2:
                raise ValueError("bad item")
            return x

        with pytest.raises(ValueError, match="bad item"):
            await StreamProcessor().process(src, bad_fn)

    @pytest.mark.asyncio
    async def test_process_async_applies_transform(self):
        finalized = []
        src = make_source("A", [1, 2, 3], finalized)

        async def double(x):
            return x * 2

        result = await StreamProcessor().process_async(src, double)
        assert result == [2, 4, 6]

    @pytest.mark.asyncio
    async def test_process_async_exception_propagates(self):
        finalized = []
        src = make_source("A", [1, 2, 3, 4, 5], finalized)

        async def bad_fn(x):
            if x == 3:
                raise RuntimeError("transform failed")
            return x

        with pytest.raises(RuntimeError, match="transform failed"):
            await StreamProcessor().process_async(src, bad_fn)


# ── finalizer on success ──────────────────────────────────────────────────────

class TestFinalizerOnSuccess:
    @pytest.mark.asyncio
    async def test_source_finalizes_after_exhaustion(self):
        finalized = []
        src = make_source("A", [1, 2, 3], finalized)
        await StreamProcessor().process(src, lambda x: x)
        assert "A" in finalized, "Source finalizer must run after normal exhaustion."

    @pytest.mark.asyncio
    async def test_async_source_finalizes_after_exhaustion(self):
        finalized = []
        src = make_source("A", [1, 2, 3], finalized)

        async def identity(x):
            return x

        await StreamProcessor().process_async(src, identity)
        assert "A" in finalized


# ── finalizer on transform exception ─────────────────────────────────────────

class TestFinalizerOnException:
    @pytest.mark.asyncio
    async def test_source_finalizes_when_fn_raises(self):
        """
        When fn() raises, the source is still mid-stream (suspended at yield).
        The processor must finalize the source before the exception reaches
        the caller — no event-loop turns happen between process() raising and
        the caller's assert.
        """
        finalized = []
        src = make_source("A", list(range(10)), finalized)

        def bad_fn(x):
            if x == 4:
                raise ValueError("stop here")
            return x

        with pytest.raises(ValueError, match="stop here"):
            await StreamProcessor().process(src, bad_fn)

        # No await between process() raising and this assertion.
        assert "A" in finalized, (
            "Source generator 'A' was abandoned mid-stream when fn() raised. "
            "The processor uses manual __anext__() iteration — unlike async for, "
            "this does not call aclose() automatically on body exception. "
            "aclose() must be awaited in a finally block to guarantee synchronous cleanup."
        )

    @pytest.mark.asyncio
    async def test_source_finalizes_when_fn_raises_on_first_item(self):
        """Even if fn() fails on the very first item, the source must finalize."""
        finalized = []
        src = make_source("A", [1, 2, 3, 4, 5], finalized)

        def always_bad(x):
            raise TypeError("rejected")

        with pytest.raises(TypeError):
            await StreamProcessor().process(src, always_bad)

        assert "A" in finalized, (
            "Source 'A' must be finalized even when fn() raises on the first item."
        )

    @pytest.mark.asyncio
    async def test_async_source_finalizes_when_async_fn_raises(self):
        """Same contract applies to process_async()."""
        finalized = []
        src = make_source("B", list(range(20)), finalized)

        async def bad_async_fn(x):
            if x == 7:
                raise RuntimeError("async fn failed")
            return x

        with pytest.raises(RuntimeError, match="async fn failed"):
            await StreamProcessor().process_async(src, bad_async_fn)

        assert "B" in finalized, (
            "Source 'B' must be finalized when the async transform raises. "
            "process_async() has the same cleanup obligation as process()."
        )

    @pytest.mark.asyncio
    async def test_source_finalizes_when_source_raises(self):
        """
        If the source itself raises mid-stream, it finalizes naturally (via the
        exception propagating through the generator frame). This confirms the
        test harness is correct — source-raised exceptions already clean up.
        """
        finalized = []
        src = make_source("C", [1, 2, 3, "bad", 5], finalized, raise_on="bad")

        with pytest.raises(ValueError):
            await StreamProcessor().process(src, lambda x: x)

        # Source raises, so its finally block runs as part of the exception
        # propagating through the generator — no aclose() needed for this path.
        assert "C" in finalized, "Source must finalize when it raises from its own body."

    @pytest.mark.asyncio
    async def test_large_source_finalizes_on_early_abort(self):
        """Source with many items: ensure it finalizes even when aborted early."""
        finalized = []
        src = make_source("D", list(range(1000)), finalized)

        def abort_at_50(x):
            if x == 50:
                raise StopIteration("early abort")  # deliberately unusual error
            return x

        with pytest.raises(StopIteration):
            await StreamProcessor().process(src, abort_at_50)

        assert "D" in finalized, "Large source must finalize on early abort."


# ── finalizer on cancellation ─────────────────────────────────────────────────

class TestFinalizerOnCancellation:
    @pytest.mark.asyncio
    async def test_source_finalizes_on_task_cancellation(self):
        """If the processing task is cancelled, the source must still finalize."""
        finalized = []

        async def infinite_source():
            try:
                i = 0
                while True:
                    yield i
                    i += 1
                    await asyncio.sleep(0.01)
            finally:
                finalized.append("infinite")

        async def slow_fn(x):
            await asyncio.sleep(0.005)
            return x

        async def run_and_cancel():
            task = asyncio.create_task(
                StreamProcessor().process_async(infinite_source(), slow_fn)
            )
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

        await run_and_cancel()
        assert "infinite" in finalized, (
            "Infinite source must finalize when the processing task is cancelled."
        )
