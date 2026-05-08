"""
Round-robin async stream multiplexer.

Interleaves items from multiple async generator streams, advancing each
stream one item per round. Streams that raise StopAsyncIteration are retired.
Streams that raise other exceptions abort the multiplexer.

Real production usage: interleaving log tails from multiple services,
merging event streams from parallel sensors, combining paginated API cursors
into a single time-ordered sequence (priority variant).

Public API:
    mux = StreamMultiplexer()
    result = asyncio.run(mux.run([stream_a(), stream_b(), stream_c()]))
    # → [a0, b0, c0, a1, b1, c1, ...]  (round-robin order)
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any


class StreamMultiplexer:
    def __init__(self):
        pass

    async def run(self, streams: list[AsyncGenerator]) -> list[Any]:
        """
        Advance all streams in round-robin order until all are exhausted.
        If any stream raises (not StopAsyncIteration), abort and re-raise.
        All stream generators must be finalized in every exit path.
        """
        # We call __anext__() manually rather than `async for` so that we can
        # interleave steps from different generators in a single loop body.
        active = list(streams)
        results: list[Any] = []

        while active:
            next_active: list[AsyncGenerator] = []
            for i, gen in enumerate(active):
                try:
                    item = await gen.__anext__()
                    results.append(item)
                    next_active.append(gen)
                except StopAsyncIteration:
                    # This generator is exhausted.
                    # Note: StopAsyncIteration is raised by the generator when its
                    # body returns. At that point the generator's frame is already
                    # cleaned up (finally blocks have run). No aclose() needed here.
                    pass
                except Exception:
                    # One generator raised. We abort the multiplexer.
                    # Before re-raising, await aclose() for every generator
                    # in both next_active (already advanced this round) and
                    # the remainder of active (not yet advanced this round).
                    for g in next_active:
                        await g.aclose()
                    for g in active[i + 1 :]:
                        await g.aclose()
                    raise
            active = next_active

        return results


# ── test helpers ──────────────────────────────────────────────────────────────

class StreamHarness:
    """Creates named async generator streams that record finalization."""

    def __init__(self):
        self.finalized: list[str] = []
        self.mux = StreamMultiplexer()

    def make_stream(
        self,
        name: str,
        items: list[Any],
        raise_on_item: Any | None = None,
    ) -> AsyncGenerator:
        finalized = self.finalized

        async def _stream():
            try:
                for item in items:
                    if item == raise_on_item:
                        raise ValueError(f"stream '{name}' rejected item {item!r}")
                    yield item
                    await asyncio.sleep(0)
            finally:
                finalized.append(name)

        return _stream()
