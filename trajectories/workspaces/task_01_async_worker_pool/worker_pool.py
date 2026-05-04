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
        self._aborting = False
        self._exceptions: list[BaseException] = []

    async def submit(self, coro: Coroutine[Any, Any, T]) -> asyncio.Task[T]:
        """Schedule a coroutine for execution. Returns the Task."""
        if self._shutdown or self._aborting:
            raise PoolShutdownError("Pool is shut down")

        await self._semaphore.acquire()
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._on_task_done)
        return task

    def _on_task_done(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        self._semaphore.release()
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            self._exceptions.append(exc)
            if not self._aborting and not self._shutdown:
                self._aborting = True
                asyncio.get_running_loop().call_soon(self._cancel_all)

    def _cancel_all(self) -> None:
        for t in list(self._tasks):
            if not t.done():
                t.cancel()

    async def shutdown(self, cancel: bool = False) -> None:
        """
        Graceful shutdown: wait for all in-flight tasks to finish.
        If cancel=True, cancel them instead.
        """
        self._shutdown = True
        if cancel:
            for t in list(self._tasks):
                if not t.done():
                    t.cancel()
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def __aenter__(self) -> "WorkerPool":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.shutdown(cancel=bool(self._exceptions))
        if exc_val is None and self._exceptions:
            raise self._exceptions[0]
