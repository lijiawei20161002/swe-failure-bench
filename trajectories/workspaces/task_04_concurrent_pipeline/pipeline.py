"""
Concurrent fan-in pipeline.

Multiple async generator sources run in parallel asyncio tasks, each feeding
items into a shared output queue. The coordinator collects all results.

Real production usage: parallel API page-fetchers, concurrent file readers,
independent data-source aggregation that must merge into one result list.

Public API:
    pipeline = FanInPipeline()

    async def source():
        for item in data:
            yield item

    results = asyncio.run(pipeline.run([source(), source()]))
    # → combined items from both sources
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any


class FanInPipeline:
    def __init__(self):
        pass

    async def run(self, sources: list[AsyncGenerator]) -> list[Any]:
        """
        Process all sources concurrently in separate asyncio tasks.
        Returns all items (order may vary). If any source raises, cancels the
        remaining tasks and re-raises. All source generators must be finalized
        (their finally blocks must run) in every exit path.
        """
        if not sources:
            return []

        output: asyncio.Queue = asyncio.Queue()
        n = len(sources)

        async def _drain(gen: AsyncGenerator) -> None:
            try:
                async for item in gen:
                    await output.put(('item', item))
                await output.put(('done',))
            except Exception as e:
                await output.put(('err', e))
            finally:
                await gen.aclose()

        tasks = [asyncio.create_task(_drain(gen)) for gen in sources]

        results: list[Any] = []
        done = 0
        try:
            while done < n:
                msg = await output.get()
                tag = msg[0]
                if tag == 'done':
                    done += 1
                elif tag == 'item':
                    results.append(msg[1])
                elif tag == 'err':
                    pending = [t for t in tasks if not t.done()]
                    for t in pending:
                        t.cancel()
                    if pending:
                        await asyncio.gather(*pending, return_exceptions=True)
                    raise msg[1]
        except BaseException:
            pending = [t for t in tasks if not t.done()]
            for t in pending:
                t.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            raise

        return results


# ── test helpers ──────────────────────────────────────────────────────────────

class SourceHarness:
    """Creates named async generator sources that record finalization."""

    def __init__(self):
        self.finalized: list[str] = []
        self.pipeline = FanInPipeline()

    def make_source(
        self,
        name: str,
        items: list[Any],
        raise_after: int | None = None,
        slow: bool = False,
    ) -> AsyncGenerator:
        finalized = self.finalized

        async def _source():
            try:
                for i, item in enumerate(items):
                    if raise_after is not None and i >= raise_after:
                        raise ValueError(f"source '{name}' error at item index {i}")
                    yield item
                    if slow:
                        await asyncio.sleep(0.02)
                    else:
                        await asyncio.sleep(0)
            finally:
                finalized.append(name)

        return _source()
