"""
Async stream processor.

Applies a transformation function to every item yielded by an async generator
source. Supports async transform functions, early termination, and structured
error handling.

Real production usage: ETL pipelines that process records from a database
cursor, HTTP response streamers that parse/validate each chunk, event handlers
that apply filters to a queue of incoming messages.

Public API:
    processor = StreamProcessor()

    async def my_source():
        for row in db.fetch_all():
            yield row

    def transform(row):
        return row["value"] * 2

    results = asyncio.run(processor.process(my_source(), transform))
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable
from typing import Any


class StreamProcessor:
    """
    Applies *fn* to each item from *source* and collects the results.

    Contract: whether the processor returns normally, the transform raises,
    or the caller cancels the pipeline, the source async generator must be
    properly finalized — its finally block must run before the exception
    reaches the caller.
    """

    async def process(self, source: AsyncGenerator, fn: Callable) -> list[Any]:
        """
        Iterate *source*, apply *fn* to each item, return collected results.
        All items are processed in order; the first exception from *fn* aborts
        the pipeline and re-raises. The source generator must be finalized on
        every exit path.
        """
        results: list[Any] = []

        # Use manual __anext__() rather than `async for` so callers can
        # interleave other logic without the implicit loop overhead.
        it = source.__aiter__()

        while True:
            try:
                item = await it.__anext__()
            except StopAsyncIteration:
                break

            # BUG: If fn(item) raises, the exception propagates out of this
            # while loop. `it` is left suspended mid-stream — its finally
            # block has NOT run. Python does not automatically call
            # it.aclose() when the iteration is abandoned after a body
            # exception; unlike sync generators, async generators are not
            # closed by CPython's reference-counting GC synchronously.
            # asyncio's asyncgen hooks will schedule aclose() for the next
            # event-loop turn, but that is too late — the caller's except
            # clause executes before any pending callbacks run.
            #
            # Fix: wrap the while loop in try/finally and `await it.aclose()`
            # in the finally block.
            result = fn(item)
            results.append(result)

        return results

    async def process_async(self, source: AsyncGenerator, fn: Callable) -> list[Any]:
        """Like process(), but fn is an async function."""
        results: list[Any] = []
        it = source.__aiter__()

        while True:
            try:
                item = await it.__anext__()
            except StopAsyncIteration:
                break
            # BUG: same missing cleanup as process() above.
            result = await fn(item)
            results.append(result)

        return results


# ── test helpers ──────────────────────────────────────────────────────────────

def make_source(
    name: str,
    items: list[Any],
    finalized: list[str],
    raise_on: Any = None,
) -> AsyncGenerator:
    """
    Async generator that yields *items* and records finalization.
    If *raise_on* is set, raises ValueError when that item is encountered.
    """
    async def _source():
        try:
            for item in items:
                if item == raise_on:
                    raise ValueError(f"source '{name}' rejected item {item!r}")
                yield item
                await asyncio.sleep(0)
        finally:
            finalized.append(name)

    return _source()
