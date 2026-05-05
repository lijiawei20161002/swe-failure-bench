"""Tests for async generator pipeline. Run: pip install pytest pytest-asyncio && pytest tests/ -x"""
import asyncio
import pytest
from pipeline import Pipeline, PipelineHarness


# ── basic correctness ─────────────────────────────────────────────────────────

class TestBasic:
    @pytest.mark.asyncio
    async def test_single_stage_transform(self):
        harness = PipelineHarness()
        harness.make_stage("double", lambda x: x * 2)
        result = await harness.run([1, 2, 3])
        assert result == [2, 4, 6]

    @pytest.mark.asyncio
    async def test_multi_stage(self):
        harness = PipelineHarness()
        harness.make_stage("double", lambda x: x * 2)
        harness.make_stage("add1", lambda x: x + 1)
        result = await harness.run([1, 2, 3])
        assert result == [3, 5, 7]

    @pytest.mark.asyncio
    async def test_empty_source(self):
        harness = PipelineHarness()
        harness.make_stage("noop")
        result = await harness.run([])
        assert result == []

    @pytest.mark.asyncio
    async def test_no_stages(self):
        p = Pipeline()
        result = await p.run([1, 2, 3])
        assert result == [1, 2, 3]


# ── finalizer runs on normal exit ─────────────────────────────────────────────

class TestFinalizerOnSuccess:
    @pytest.mark.asyncio
    async def test_single_stage_finalizer_runs(self):
        """After a successful run, all stage generators must have finalized."""
        harness = PipelineHarness()
        harness.make_stage("A")
        await harness.run([1, 2, 3])
        assert "A" in harness.finalized, (
            "Stage A finalizer (finally block) must run after normal pipeline completion. "
            "Generators are not guaranteed to finalize unless aclose() is called."
        )

    @pytest.mark.asyncio
    async def test_all_stages_finalize_on_success(self):
        harness = PipelineHarness()
        harness.make_stage("A")
        harness.make_stage("B")
        harness.make_stage("C")
        await harness.run([1, 2, 3])
        assert set(harness.finalized) == {"A", "B", "C"}, (
            f"All stage finalizers must run. Got: {harness.finalized}"
        )


# ── finalizer runs on exception ───────────────────────────────────────────────

class TestFinalizerOnException:
    @pytest.mark.asyncio
    async def test_finalizer_runs_when_stage_raises(self):
        """
        If a stage raises mid-pipeline, ALL other stages must still finalize.
        """
        finalized = []
        pipeline = Pipeline()

        @pipeline.stage
        async def normal_stage(items):
            try:
                async for item in items:
                    yield item
            finally:
                finalized.append("normal")

        @pipeline.stage
        async def exploding_stage(items):
            try:
                async for item in items:
                    if item == 2:
                        raise ValueError("boom")
                    yield item
            finally:
                finalized.append("exploding")

        with pytest.raises(ValueError, match="boom"):
            await pipeline.run([1, 2, 3])

        assert "exploding" in finalized, "exploding_stage finalizer must run"
        assert "normal" in finalized, (
            "normal_stage finalizer must run even though a downstream stage raised. "
            "BUG: upstream generators are not closed on exception propagation."
        )

    @pytest.mark.asyncio
    async def test_upstream_finalizer_runs_on_downstream_exception(self):
        finalized = []
        pipeline = Pipeline()

        @pipeline.stage
        async def upstream(items):
            try:
                async for item in items:
                    yield item
            finally:
                finalized.append("upstream")

        @pipeline.stage
        async def downstream(items):
            try:
                count = 0
                async for item in items:
                    count += 1
                    if count == 2:
                        raise RuntimeError("downstream error")
                    yield item
            finally:
                finalized.append("downstream")

        with pytest.raises(RuntimeError):
            await pipeline.run([1, 2, 3, 4])

        assert "upstream" in finalized, (
            "upstream generator must be aclose()d when a downstream generator raises. "
            "Iteration order means the upstream generator may be suspended mid-yield."
        )


# ── finalizer runs on early cancel ────────────────────────────────────────────

class TestFinalizerOnCancel:
    @pytest.mark.asyncio
    async def test_finalizers_run_on_early_break(self):
        """
        When run_with_cancel() breaks early, ALL stage generators must finalize.
        """
        harness = PipelineHarness()
        harness.make_stage("A")
        harness.make_stage("B")
        await harness.run_with_cancel([1, 2, 3, 4, 5], cancel_after=2)
        assert set(harness.finalized) == {"A", "B"}, (
            f"All stage finalizers must run after early break. Got: {harness.finalized}. "
            "When the consumer breaks out of `async for gen`, the generator itself "
            "finalizes (downstream), but upstream generators only finalize if "
            "aclose() is explicitly awaited."
        )

    @pytest.mark.asyncio
    async def test_only_requested_items_returned_on_cancel(self):
        harness = PipelineHarness()
        harness.make_stage("double", lambda x: x * 2)
        result = await harness.run_with_cancel([1, 2, 3, 4, 5], cancel_after=3)
        assert result == [2, 4, 6]

    @pytest.mark.asyncio
    async def test_finalizer_runs_on_asyncio_cancellation(self):
        """
        If the pipeline task itself is cancelled via asyncio.CancelledError,
        all stage finalizers must still run.
        """
        finalized = []
        pipeline = Pipeline()

        @pipeline.stage
        async def slow_stage(items):
            try:
                async for item in items:
                    await asyncio.sleep(10)   # will be cancelled
                    yield item
            finally:
                finalized.append("slow")

        async def run_and_cancel():
            task = asyncio.create_task(pipeline.run([1, 2, 3]))
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        await run_and_cancel()
        assert "slow" in finalized, (
            "Stage finalizer must run when the pipeline task is asyncio-cancelled."
        )


# ── ordering of finalization ──────────────────────────────────────────────────

class TestFinalizationOrder:
    @pytest.mark.asyncio
    async def test_stages_finalize_downstream_first(self):
        """
        Stages should finalize in reverse order (downstream first, then upstream).
        This matches LIFO semantics: the last stage created is the first one
        whose generator is exhausted, so its finally runs first.
        """
        order = []
        pipeline = Pipeline()

        @pipeline.stage
        async def A(items):
            try:
                async for x in items: yield x
            finally:
                order.append("A")

        @pipeline.stage
        async def B(items):
            try:
                async for x in items: yield x
            finally:
                order.append("B")

        @pipeline.stage
        async def C(items):
            try:
                async for x in items: yield x
            finally:
                order.append("C")

        await pipeline.run([1])
        # C is downstream-most, exhausts first; then B; then A
        assert order == ["C", "B", "A"], (
            f"Expected finalization order C→B→A (downstream first), got {order}"
        )
