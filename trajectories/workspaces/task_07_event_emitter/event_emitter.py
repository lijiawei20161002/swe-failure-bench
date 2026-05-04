"""
Event emitter with wildcard subscriptions and weak-reference handlers.

Modelled after Node.js EventEmitter / Python's blinker library.

Features:
  - Exact-match listeners: emitter.on("user.login", handler)
  - Wildcard listeners: emitter.on("user.*", handler)
      Wildcards use glob-style matching (* matches one segment, ** matches any).
  - Weak-reference support: handlers that are bound methods or lambdas stored
    as weakrefs so they don't prevent garbage collection.
  - Per-listener error isolation: an exception in one listener must not
    prevent subsequent listeners from running.
  - once(): fire handler exactly once, then auto-unsubscribe.

Public API:
    em = EventEmitter()
    em.on("order.created", handler)
    em.once("order.created", one_time_handler)
    em.emit("order.created", order_data)
    em.off("order.created", handler)
"""

from __future__ import annotations

import inspect
import weakref
from collections import defaultdict
from typing import Any, Callable


class EventEmitter:
    def __init__(self):
        # pattern → list of _Handler
        self._listeners: dict[str, list[_Handler]] = defaultdict(list)
        self._errors: list[Exception] = []   # collected handler errors

    # ── subscription ──────────────────────────────────────────────────────────

    def on(self, event: str, handler: Callable, *, weak: bool = True) -> None:
        """Subscribe *handler* to *event* (glob pattern supported)."""
        self._listeners[event].append(_Handler(handler, once=False, weak=weak))

    def once(self, event: str, handler: Callable, *, weak: bool = True) -> None:
        """Subscribe *handler* to fire exactly once on *event*."""
        self._listeners[event].append(_Handler(handler, once=True, weak=weak))

    def off(self, event: str, handler: Callable) -> None:
        """Remove *handler* from *event*. No-op if not subscribed."""
        if event not in self._listeners:
            return
        self._listeners[event] = [
            h for h in self._listeners[event]
            if not h.matches(handler)
        ]

    # ── emission ──────────────────────────────────────────────────────────────

    def emit(self, event: str, *args, **kwargs) -> int:
        """
        Fire all handlers matching *event*.
        Returns the number of handlers called.
        Exceptions from handlers are collected in self._errors but do NOT
        propagate — all matching handlers are always called.
        """
        called = 0
        to_remove: list[tuple[str, _Handler]] = []

        for pattern, handlers in list(self._listeners.items()):
            if not _matches(pattern, event):
                continue

            for h in list(handlers):
                fn = h.resolve()
                if fn is None:
                    # Weak ref is dead — mark for cleanup
                    to_remove.append((pattern, h))
                    continue
                try:
                    fn(*args, **kwargs)
                    called += 1
                except Exception as exc:
                    self._errors.append(exc)

                if h.once:
                    to_remove.append((pattern, h))

        # Cleanup
        for pattern, h in to_remove:
            try:
                self._listeners[pattern].remove(h)
            except ValueError:
                pass

        return called

    # ── introspection ─────────────────────────────────────────────────────────

    def listener_count(self, event: str) -> int:
        """Return number of live listeners for exact *event* pattern."""
        return len([h for h in self._listeners.get(event, []) if h.resolve() is not None])

    def clear_errors(self) -> list[Exception]:
        errs, self._errors = self._errors, []
        return errs


# ── internals ─────────────────────────────────────────────────────────────────

def _matches(pattern: str, event: str) -> bool:
    """
    Return True if *event* matches *pattern* using glob rules:
      *   matches one dot-separated segment
      **  matches any number of segments (including zero)
    E.g.:
      "user.*"   matches "user.login", "user.logout" but NOT "user.login.extra"
      "order.**" matches "order.created", "order.payment.done"
      "user.*"   does NOT match "user" (must have exactly one segment after)
    """
    p_parts = pattern.split('.')
    e_parts = event.split('.')

    from functools import lru_cache

    @lru_cache(maxsize=None)
    def match(pi: int, ei: int) -> bool:
        if pi == len(p_parts) and ei == len(e_parts):
            return True
        if pi == len(p_parts):
            return False
        if ei == len(e_parts):
            # Only ** can match empty remaining event segments
            return p_parts[pi] == '**' and match(pi + 1, ei)

        pp = p_parts[pi]
        if pp == '**':
            # ** matches zero or more segments
            for k in range(ei, len(e_parts) + 1):
                if match(pi + 1, k):
                    return True
            return False
        elif pp == '*':
            return match(pi + 1, ei + 1)
        else:
            return pp == e_parts[ei] and match(pi + 1, ei + 1)

    return match(0, 0)


class _Handler:
    __slots__ = ("_ref", "once", "_is_weak", "_id")

    def __init__(self, fn: Callable, *, once: bool, weak: bool):
        self.once = once
        self._is_weak = weak
        self._id = id(fn)
        if weak:
            try:
                if inspect.ismethod(fn):
                    self._ref = weakref.WeakMethod(fn)
                else:
                    self._ref = weakref.ref(fn)
            except TypeError:
                # Some callables (builtins) can't be weakly referenced
                self._ref = fn
                self._is_weak = False
        else:
            self._ref = fn

    def resolve(self) -> Callable | None:
        if self._is_weak:
            return self._ref()
        return self._ref

    def matches(self, fn: Callable) -> bool:
        # Bound methods are transient objects, so id()/is comparison doesn't work
        if inspect.ismethod(fn):
            resolved = self.resolve()
            if resolved is None:
                return False
            if not inspect.ismethod(resolved):
                return False
            return (
                resolved.__func__ is fn.__func__
                and resolved.__self__ is fn.__self__
            )
        return self._id == id(fn) or self.resolve() is fn
