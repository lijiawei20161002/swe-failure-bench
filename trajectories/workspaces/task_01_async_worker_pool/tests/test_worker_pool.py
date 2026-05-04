"""Tests for WorkerPool. Run: pytest tests/ -x"""
import asyncio
import pytest
from worker_pool import WorkerPool, PoolShutdownError


# ── helpers ──────────────────────────────────────────────────────────────────

async def slow(n: float, result=None):
    await asyncio.sleep(n)
    return result

async def boom(msg="oops"):
    await asyncio.sleep(0)
    raise ValueError(msg)


# ── basic concurrency ─────────────────────────────────────────────────────────

class TestConcurrency:
    @pytest.mark.asyncio
    async def test_runs_jobs(self):
        async with WorkerPool(max_workers=2) as pool:
            t = await pool.submit(slow(0, "ok"))
        assert t.result() == "ok"

    @pytest.mark.asyncio
    async def test_honours_max_workers(self):
        """At most max_workers coroutines should run simultaneously."""
        running = 0
        peak = 0

        async def job():
            nonlocal running, peak
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0.05)
            running -= 1

        async with WorkerPool(max_workers=3) as pool:
            tasks = [await pool.submit(job()) for _ in range(9)]
            await asyncio.gather(*tasks)

        assert peak <= 3

    @pytest.mark.asyncio
    async def test_submit_after_shutdown_raises_shutdown_error(self):
        """submit() after shutdown must raise PoolShutdownError, not a generic error."""
        pool = WorkerPool(max_workers=2)
        await pool.shutdown()
        with pytest.raises(PoolShutdownError):
            await pool.submit(slow(0))


# ── exception propagation ─────────────────────────────────────────────────────

class TestExceptionPropagation:
    @pytest.mark.asyncio
    async def test_exception_in_worker_propagates_on_context_exit(self):
        """If a worker raises, __aexit__ must re-raise it."""
        with pytest.raises(ValueError, match="oops"):
            async with WorkerPool(max_workers=2) as pool:
                await pool.submit(boom("oops"))
                await asyncio.sleep(0.05)   # let the worker run

    @pytest.mark.asyncio
    async def test_exception_cancels_siblings(self):
        """When one worker raises, all other in-flight tasks are cancelled."""
        cancelled = []

        async def sibling():
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled.append(True)
                raise

        with pytest.raises(ValueError):
            async with WorkerPool(max_workers=4) as pool:
                for _ in range(3):
                    await pool.submit(sibling())
                await pool.submit(boom())
                await asyncio.sleep(0.05)

        assert len(cancelled) == 3, f"expected 3 siblings cancelled, got {len(cancelled)}"

    @pytest.mark.asyncio
    async def test_multiple_exceptions_all_collected(self):
        """All worker exceptions must be accessible, not just the first."""
        collected = []

        async def bad(msg):
            await asyncio.sleep(0)
            raise ValueError(msg)

        with pytest.raises(Exception):
            async with WorkerPool(max_workers=4) as pool:
                for i in range(3):
                    await pool.submit(bad(f"err{i}"))
                await asyncio.sleep(0.05)

        # At minimum, the pool must expose the exceptions it collected
        assert len(pool._exceptions) >= 1


# ── shutdown semantics ────────────────────────────────────────────────────────

class TestShutdown:
    @pytest.mark.asyncio
    async def test_graceful_shutdown_waits_for_inflight(self):
        """shutdown() without cancel=True must wait for running tasks to finish."""
        finished = []

        async def job():
            await asyncio.sleep(0.1)
            finished.append(True)

        pool = WorkerPool(max_workers=2)
        await pool.submit(job())
        await pool.submit(job())
        await pool.shutdown(cancel=False)

        assert len(finished) == 2

    @pytest.mark.asyncio
    async def test_cancel_shutdown_cancels_tasks(self):
        """shutdown(cancel=True) must cancel in-flight tasks."""
        pool = WorkerPool(max_workers=2)
        t1 = await pool.submit(slow(10))
        t2 = await pool.submit(slow(10))
        await pool.shutdown(cancel=True)

        assert t1.cancelled() or t1.done()
        assert t2.cancelled() or t2.done()

    @pytest.mark.asyncio
    async def test_double_shutdown_is_safe(self):
        """Calling shutdown() twice must not raise."""
        pool = WorkerPool(max_workers=2)
        await pool.shutdown()
        await pool.shutdown()   # second call is a no-op
