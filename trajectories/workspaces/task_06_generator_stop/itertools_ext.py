"""
Extended iteration utilities for data processing pipelines.

Provides iterator helpers that complement the standard `itertools` module:

- chunked(iterable, size)      — yield fixed-size chunks
- sliding_window(iterable, n)  — yield overlapping windows of width n
- interleave(*iterables)       — round-robin merge of multiple iterables
- take_while_inclusive(pred, iterable) — like takewhile but includes first
                                          failing element
- flatten(nested)              — recursively flatten nested iterables

All functions return generators; they work with any iterable and produce
results lazily.
"""

from __future__ import annotations

import itertools
from typing import Any, Callable, Generator, Iterable, Iterator, TypeVar

T = TypeVar("T")


def chunked(iterable: Iterable[T], size: int) -> Generator[list[T], None, None]:
    """
    Yield successive non-overlapping chunks of *size* items from *iterable*.

    The last chunk may be smaller than *size* if the iterable length is not
    evenly divisible.

    Example:
        list(chunked(range(7), 3))  → [[0,1,2], [3,4,5], [6]]
    """
    if size <= 0:
        raise ValueError(f"size must be positive, got {size!r}")

    it = iter(iterable)
    while chunk := list(itertools.islice(it, size)):
        yield chunk


def sliding_window(
    iterable: Iterable[T], n: int
) -> Generator[tuple[T, ...], None, None]:
    """
    Yield overlapping tuples of width *n*.

    Example:
        list(sliding_window("ABCDE", 3))  → [('A','B','C'), ('B','C','D'), ('C','D','E')]
    """
    if n <= 0:
        raise ValueError(f"n must be positive, got {n!r}")

    from collections import deque
    it = iter(iterable)
    window: deque[T] = deque(maxlen=n)

    # Prime the window
    try:
        for _ in range(n):
            window.append(next(it))
    except StopIteration:
        return   # iterable shorter than window — yield nothing

    yield tuple(window)
    for item in it:
        window.append(item)
        yield tuple(window)


def interleave(*iterables: Iterable[T]) -> Generator[T, None, None]:
    """
    Round-robin merge: yield one item from each iterable in turn.
    Stops when the shortest iterable is exhausted.

    Example:
        list(interleave([1,2,3], ['a','b','c']))  → [1,'a',2,'b',3,'c']
    """
    for group in zip(*iterables):
        yield from group


def take_while_inclusive(
    pred: Callable[[T], bool], iterable: Iterable[T]
) -> Generator[T, None, None]:
    """
    Yield items while pred(item) is True, plus the first item where it fails.

    Example:
        list(take_while_inclusive(lambda x: x < 5, range(10)))  → [0,1,2,3,4,5]
    """
    for item in iterable:
        yield item
        if not pred(item):
            return


def flatten(nested: Iterable[Any], depth: int = -1) -> Generator[Any, None, None]:
    """
    Recursively flatten nested iterables up to *depth* levels.
    depth=-1 means flatten fully.

    Strings and bytes are not flattened (treated as atomic).

    Example:
        list(flatten([[1, [2, 3]], [4, [5, [6]]]], depth=1))  → [1,[2,3],4,[5,[6]]]
        list(flatten([[1, [2, 3]], [4, [5, [6]]]]))            → [1,2,3,4,5,6]
    """
    for item in nested:
        if (
            isinstance(item, Iterable)
            and not isinstance(item, (str, bytes))
            and depth != 0
        ):
            yield from flatten(item, depth - 1 if depth > 0 else -1)
        else:
            yield item
