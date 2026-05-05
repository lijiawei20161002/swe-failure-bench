"""
Async worker pool — processes jobs from a queue with bounded concurrency.

Based on patterns from aiohttp / anyio task groups.

Public API:
    pool = WorkerPool(max_workers=4)
    async with pool:
        result = await pool.submit(coro)
        await pool.shutdown()   # graceful: wait for in-flight jobs
"""

from __future__ import annotations

import asyncio
from typing import Any, Coroutine, TypeVar

T = TypeVar("T")


class WorkerPoolError(Exception):
    pass


class PoolShutdownError(WorkerPoolError):
    """Raised when submit() is called after shutdown."""
    pass


class WorkerPool:
    def __init__(self, max_workers: int = 4):
        if max_workers < 1:
            raise ValueError("max_workers must be >= 1")
        self._max_workers = max_workers
        self._semaphore = asyncio.Semaphore(max_workers)
        self._tasks: set[asyncio.Task] = set()
        self._shutdown = False
        self._exceptions: list[BaseException] = []

    async def submit(self, coro: Coroutine[Any, Any, T]) -> asyncio.Task[T]:
        """Schedule a coroutine for execution. Returns the Task."""
        if self._shutdown:
            raise PoolShutdownError("Pool is shut down")

        await self._semaphore.acquire()
        task = asyncio.create_task(self._run(coro))
        self._tasks.add(task)
        return task

    async def _run(self, coro: Coroutine[Any, Any, T]) -> T:
        try:
            return await coro
        except Exception as exc:
            self._exceptions.append(exc)
            current = asyncio.current_task()
            for t in list(self._tasks):
                if t is not current and not t.done():
                    t.cancel()
            raise
        finally:
            self._semaphore.release()

    async def shutdown(self, cancel: bool = False) -> None:
        """
        Graceful shutdown: wait for all in-flight tasks to finish.
        If cancel=True, cancel them instead.
        """
        self._shutdown = True
        tasks = list(self._tasks)
        if cancel:
            for t in tasks:
                if not t.done():
                    t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    async def __aenter__(self) -> "WorkerPool":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.shutdown()
        if exc_type is None and self._exceptions:
            raise self._exceptions[0]
