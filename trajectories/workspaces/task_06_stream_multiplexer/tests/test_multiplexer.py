"""Tests for round-robin stream multiplexer. Run: pip install pytest pytest-asyncio && pytest tests/ -x"""
import asyncio
import pytest
from multiplexer import StreamMultiplexer, StreamHarness


# ── basic correctness ─────────────────────────────────────────────────────────

class TestBasic:
    @pytest.mark.asyncio
    async def test_single_stream(self):
        harness = StreamHarness()
        result = await harness.mux.run([harness.make_stream("A", [1, 2, 3])])
        assert result == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_round_robin_two_streams(self):
        harness = StreamHarness()
        result = await harness.mux.run([
            harness.make_stream("A", [1, 2, 3]),
            harness.make_stream("B", [4, 5, 6]),
        ])
        # Round-robin: A0, B0, A1, B1, A2, B2
        assert result == [1, 4, 2, 5, 3, 6]

    @pytest.mark.asyncio
    async def test_unequal_length_streams(self):
        harness = StreamHarness()
        result = await harness.mux.run([
            harness.make_stream("A", [1, 2, 3]),
            harness.make_stream("B", [10]),
        ])
        assert result == [1, 10, 2, 3]

    @pytest.mark.asyncio
    async def test_empty_streams(self):
        harness = StreamHarness()
        result = await harness.mux.run([])
        assert result == []

    @pytest.mark.asyncio
    async def test_exception_propagates(self):
        harness = StreamHarness()
        with pytest.raises(ValueError):
            await harness.mux.run([
                harness.make_stream("A", [1, 2, 3]),
                harness.make_stream("B", [4, 5], raise_on_item=5),
            ])


# ── finalizer on success ──────────────────────────────────────────────────────

class TestFinalizerOnSuccess:
    @pytest.mark.asyncio
    async def test_all_streams_finalize_on_exhaustion(self):
        harness = StreamHarness()
        await harness.mux.run([
            harness.make_stream("A", [1, 2]),
            harness.make_stream("B", [3, 4]),
            harness.make_stream("C", [5]),
        ])
        assert set(harness.finalized) == {"A", "B", "C"}, (
            f"All stream finalizers must run after normal exhaustion. "
            f"Got: {harness.finalized}"
        )


# ── finalizer on exception ────────────────────────────────────────────────────

class TestFinalizerOnException:
    @pytest.mark.asyncio
    async def test_surviving_streams_finalize_when_one_raises(self):
        """
        When stream B raises, the multiplexer aborts. Streams A and C are
        still suspended mid-iteration. Because the multiplexer uses manual
        __anext__() calls rather than `async for`, Python does NOT implicitly
        close the surviving generators. aclose() must be explicitly called.
        """
        harness = StreamHarness()
        with pytest.raises(ValueError):
            await harness.mux.run([
                harness.make_stream("A", [1, 2, 3, 4, 5]),
                harness.make_stream("B", [10, 20], raise_on_item=20),
                harness.make_stream("C", [100, 200, 300]),
            ])

        assert "B" in harness.finalized, "Raising stream B must finalize"
        assert "A" in harness.finalized, (
            "Stream A was suspended when B raised, but its generator was never "
            "aclose()d. The multiplexer uses __anext__() directly — unlike async for, "
            "manual iteration does not call aclose() on abort. "
            "aclose() must be awaited explicitly for each surviving generator."
        )
        assert "C" in harness.finalized, (
            "Stream C was suspended when B raised, but its generator was never "
            "aclose()d."
        )

    @pytest.mark.asyncio
    async def test_finalizers_run_before_exception_reaches_caller(self):
        """No await between mux.run() and the assertion — finalizers must be synchronous."""
        finalized = []

        async def long_stream(name):
            try:
                for i in range(1000):
                    yield i
                    await asyncio.sleep(0)
            finally:
                finalized.append(name)

        async def erroring_stream():
            try:
                yield 1
                yield 2
                raise RuntimeError("stream error")
            finally:
                finalized.append("erroring")

        mux = StreamMultiplexer()
        with pytest.raises(RuntimeError, match="stream error"):
            await mux.run([long_stream("L1"), long_stream("L2"), erroring_stream()])

        assert "L1" in finalized, (
            "L1 not finalized synchronously. When the multiplexer catches the "
            "exception, it must await aclose() on all surviving generators before "
            "re-raising, so that cleanup is not deferred to asyncio's GC hooks."
        )
        assert "L2" in finalized, "L2 not finalized synchronously."

    @pytest.mark.asyncio
    async def test_already_advanced_generators_finalize_on_exception(self):
        """
        Generators that were already advanced this round (in next_active) must
        also be finalized, not just the ones still waiting in active.
        """
        harness = StreamHarness()
        # A is advanced first in the round, then B raises.
        # At the moment B raises, A is already in next_active — it must still finalize.
        with pytest.raises(ValueError):
            await harness.mux.run([
                harness.make_stream("A", [1, 2, 3, 4]),
                harness.make_stream("B", [10], raise_on_item=10),
            ])
        assert "A" in harness.finalized, (
            "Stream A was already advanced this round when B raised. "
            "It's in next_active, which is abandoned without cleanup."
        )

    @pytest.mark.asyncio
    async def test_three_streams_all_finalize_on_middle_raise(self):
        harness = StreamHarness()
        with pytest.raises(ValueError):
            await harness.mux.run([
                harness.make_stream("first", [1, 2, 3, 4, 5]),
                harness.make_stream("middle", [10, 20], raise_on_item=20),
                harness.make_stream("last", [100, 200, 300, 400, 500]),
            ])
        missing = [name for name in ("first", "middle", "last")
                   if name not in harness.finalized]
        assert not missing, (
            f"These streams were not finalized: {missing}. "
            f"Finalized: {harness.finalized}"
        )
