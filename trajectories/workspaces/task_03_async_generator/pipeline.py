"""
Async generator pipeline with backpressure and cancellation.

A chain of async generators processes items through stages. Each stage
is an async generator that transforms items. The pipeline supports:
  - Backpressure: downstream stages that are slow pause upstream ones
  - Cancellation: cancelling the pipeline must cleanly finalize all stages
    (their finally blocks must run even if the stage was mid-yield)
  - Exception propagation: an exception in any stage must cancel the others
    and propagate out of pipeline.run()

Real production usage: streaming ETL pipelines, async data processing
(e.g., aiofiles reader → transformer → aiohttp writer).

Public API:
    pipeline = Pipeline()

    @pipeline.stage
    async def double(items):
        async for x in items:
            yield x * 2

    result = asyncio.run(pipeline.run([1, 2, 3]))
    # → [2, 4, 6]
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, AsyncIterable
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class PipelineError(Exception):
    pass


class Pipeline:
    def __init__(self):
        self._stages: list[Callable] = []
        self._finalizers: list[str] = []   # records which stages finalized (for tests)

    def stage(self, fn: Callable) -> Callable:
        """Register an async generator function as a pipeline stage."""
        self._stages.append(fn)
        return fn

    async def run(self, source: list[Any]) -> list[Any]:
        """
        Run the pipeline over *source* and return all output items.
        All stage generators must be properly closed even if an error occurs.
        """
        async def _source_gen() -> AsyncGenerator:
            for item in source:
                yield item

        current: AsyncIterable = _source_gen()
        generators = [current]

        for stage_fn in self._stages:
            gen = stage_fn(current)
            generators.append(gen)
            current = gen

        results = []
        try:
            async for item in current:
                results.append(item)
                if len(results) >= len(source):
                    break
        finally:
            for gen in reversed(generators):
                try:
                    await gen.aclose()
                except Exception:
                    pass

        return results

    async def run_with_cancel(self, source: list[Any], cancel_after: int) -> list[Any]:
        """
        Run pipeline but cancel after *cancel_after* items are produced.
        All stage generators must still finalize (run their finally blocks).
        """
        async def _source_gen() -> AsyncGenerator:
            for item in source:
                yield item

        current: AsyncIterable = _source_gen()
        generators = [current]

        for stage_fn in self._stages:
            gen = stage_fn(current)
            generators.append(gen)
            current = gen

        results = []
        try:
            async for item in current:
                results.append(item)
                if len(results) >= cancel_after:
                    break
        finally:
            for gen in reversed(generators):
                try:
                    await gen.aclose()
                except Exception:
                    pass

        return results


# ── helpers for tests ─────────────────────────────────────────────────────────

class PipelineHarness:
    """Wraps Pipeline and records which stage finalizers ran."""

    def __init__(self):
        self.finalized: list[str] = []
        self.pipeline = Pipeline()

    def make_stage(self, name: str, transform=None):
        finalized = self.finalized
        pipeline = self.pipeline

        async def _stage(items):
            try:
                async for item in items:
                    yield transform(item) if transform else item
            finally:
                finalized.append(name)

        _stage.__name__ = name
        pipeline.stage(_stage)
        return _stage

    async def run(self, source):
        return await self.pipeline.run(source)

    async def run_with_cancel(self, source, cancel_after):
        return await self.pipeline.run_with_cancel(source, cancel_after)
