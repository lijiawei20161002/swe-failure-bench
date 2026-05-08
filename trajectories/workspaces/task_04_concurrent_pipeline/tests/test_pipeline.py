"""Tests for concurrent fan-in pipeline. Run: pip install pytest pytest-asyncio && pytest tests/ -x"""
import asyncio
import pytest
from pipeline import FanInPipeline, SourceHarness


# ── basic correctness ─────────────────────────────────────────────────────────

class TestBasic:
    @pytest.mark.asyncio
    async def test_single_source(self):
        harness = SourceHarness()
        result = await harness.pipeline.run([harness.make_source("A", [1, 2, 3])])
        assert sorted(result) == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_multiple_sources_combined(self):
        harness = SourceHarness()
        result = await harness.pipeline.run([
            harness.make_source("A", [1, 2]),
            harness.make_source("B", [3, 4]),
        ])
        assert sorted(result) == [1, 2, 3, 4]

    @pytest.mark.asyncio
    async def test_empty_sources_list(self):
        harness = SourceHarness()
        result = await harness.pipeline.run([])
        assert result == []

    @pytest.mark.asyncio
    async def test_exception_propagates(self):
        harness = SourceHarness()
        with pytest.raises(ValueError, match="source 'B' error"):
            await harness.pipeline.run([
                harness.make_source("A", [1, 2, 3]),
                harness.make_source("B", [10, 20], raise_after=1),
            ])


# ── finalizer on success ──────────────────────────────────────────────────────

class TestFinalizerOnSuccess:
    @pytest.mark.asyncio
    async def test_all_sources_finalize_on_success(self):
        harness = SourceHarness()
        await harness.pipeline.run([
            harness.make_source("A", [1]),
            harness.make_source("B", [2]),
            harness.make_source("C", [3]),
        ])
        assert set(harness.finalized) == {"A", "B", "C"}, (
            f"All source finalizers must run after successful completion. "
            f"Got: {harness.finalized}"
        )

    @pytest.mark.asyncio
    async def test_single_source_finalizes(self):
        harness = SourceHarness()
        await harness.pipeline.run([harness.make_source("A", [1, 2, 3])])
        assert "A" in harness.finalized


# ── finalizer on exception ────────────────────────────────────────────────────

class TestFinalizerOnException:
    @pytest.mark.asyncio
    async def test_surviving_sources_finalize_when_one_raises(self):
        """
        When source B raises, the pipeline cancels sources A and C.
        Even though A and C were cancelled (not exhausted), their async
        generators must still be finalized — aclose() must be awaited.
        """
        harness = SourceHarness()
        with pytest.raises(ValueError):
            await harness.pipeline.run([
                harness.make_source("A", list(range(50)), slow=True),
                harness.make_source("B", [10, 20], raise_after=1),
                harness.make_source("C", list(range(50)), slow=True),
            ])

        assert "B" in harness.finalized, "Raising source B must finalize"
        assert "A" in harness.finalized, (
            "Source A was cancelled when B raised, but its async generator was "
            "never aclose()d. Async generators do not finalize automatically on "
            "task cancellation — aclose() must be explicitly awaited."
        )
        assert "C" in harness.finalized, (
            "Source C was cancelled when B raised, but its async generator was "
            "never aclose()d."
        )

    @pytest.mark.asyncio
    async def test_finalizers_run_before_exception_reaches_caller(self):
        """
        All finalizers must have run by the time the exception reaches the caller —
        no await between pipeline.run() and the assertion.
        """
        finalized = []

        async def slow_source(name):
            try:
                for i in range(100):
                    yield i
                    await asyncio.sleep(0)
            finally:
                finalized.append(name)

        async def erroring_source():
            try:
                yield 1
                raise RuntimeError("boom")
            finally:
                finalized.append("erroring")

        pipeline = FanInPipeline()
        with pytest.raises(RuntimeError, match="boom"):
            await pipeline.run([slow_source("slow1"), slow_source("slow2"), erroring_source()])

        # No await between pipeline.run() and these assertions.
        assert "slow1" in finalized, (
            "'slow1' generator not finalized. When the pipeline task catches the "
            "exception and cancels sibling tasks, it must await aclose() on each "
            "source generator so finalization is synchronous, not deferred."
        )
        assert "slow2" in finalized, "'slow2' generator not finalized."

    @pytest.mark.asyncio
    async def test_two_sources_both_finalize_when_first_raises(self):
        harness = SourceHarness()
        with pytest.raises(ValueError):
            await harness.pipeline.run([
                harness.make_source("raiser", [0], raise_after=0),
                harness.make_source("victim", list(range(10)), slow=True),
            ])
        assert "victim" in harness.finalized, (
            "'victim' source was running when 'raiser' failed, but its generator "
            "was not finalized. Its task was cancelled without aclose() being called."
        )


# ── finalizer on pipeline cancellation ───────────────────────────────────────

class TestFinalizerOnCancellation:
    @pytest.mark.asyncio
    async def test_sources_finalize_when_pipeline_task_is_cancelled(self):
        finalized = []

        async def infinite(name):
            try:
                i = 0
                while True:
                    yield i
                    i += 1
                    await asyncio.sleep(0.01)
            finally:
                finalized.append(name)

        pipeline = FanInPipeline()

        async def run_and_cancel():
            task = asyncio.create_task(pipeline.run([infinite("X"), infinite("Y")]))
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

        await run_and_cancel()
        assert "X" in finalized, "Generator X must finalize on pipeline cancellation"
        assert "Y" in finalized, "Generator Y must finalize on pipeline cancellation"
