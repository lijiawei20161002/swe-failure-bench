"""
Lightweight publish-subscribe event bus.

Listeners register a callable to be invoked when a named event is emitted.
The bus holds listeners weakly so that objects can subscribe without
preventing their own garbage collection — the subscription is automatically
removed when the subscriber is collected.

Public API:
    bus = EventBus()

    class MyHandler:
        def on_ready(self, data):
            print("ready:", data)

    h = MyHandler()
    bus.subscribe("ready", h.on_ready)
    bus.emit("ready", {"status": "ok"})   # calls h.on_ready({"status": "ok"})
    del h
    bus.emit("ready", {})   # no-op: h was collected, subscription auto-removed
"""

from __future__ import annotations

import inspect
import weakref
from typing import Any, Callable


class _Listener:
    """Internal wrapper holding either a strong reference or a WeakMethod."""

    __slots__ = ("_ref", "_strong")

    def __init__(self, callback: Callable[[Any], None]) -> None:
        if inspect.ismethod(callback):
            # Use WeakMethod so the subscription disappears when the
            # underlying object is garbage-collected.
            try:
                self._ref = weakref.WeakMethod(callback)
                self._strong = None
            except TypeError:
                # The instance does not support weak references – fall back
                # to a strong reference.
                self._ref = None
                self._strong = callback
        else:
            self._ref = None
            self._strong = callback

    def is_alive(self) -> bool:
        if self._strong is not None:
            return True
        return self._ref is not None and self._ref() is not None

    def call(self, data: Any) -> bool:
        """Invoke the callback if alive. Returns True if called, False if dead."""
        if self._strong is not None:
            self._strong(data)
            return True
        fn = self._ref()
        if fn is not None:
            fn(data)
            return True
        return False


def _make_key(callback: Callable[[Any], None]) -> Any:
    """Return a stable key for *callback*."""
    if inspect.ismethod(callback):
        # Bound methods are ephemeral objects – identify them by the
        # identity of the underlying instance and function instead.
        return (id(callback.__self__), id(callback.__func__))
    return id(callback)


class EventBus:
    """
    Pub/sub bus with weak-reference listener storage.

    Stores listeners as weak references so that subscribing to an event
    does not prevent the subscriber from being garbage-collected.  When the
    subscriber is collected the corresponding subscription is automatically
    removed from the bus.
    """

    def __init__(self) -> None:
        self._listeners: dict[str, dict[Any, _Listener]] = {}

    def subscribe(self, event: str, callback: Callable[[Any], None]) -> None:
        """Register *callback* to be called when *event* is emitted."""
        if event not in self._listeners:
            self._listeners[event] = {}
        key = _make_key(callback)
        self._listeners[event][key] = _Listener(callback)

    def unsubscribe(self, event: str, callback: Callable[[Any], None]) -> None:
        """Remove a previously registered callback."""
        listeners = self._listeners.get(event)
        if listeners is not None:
            key = _make_key(callback)
            listeners.pop(key, None)

    def emit(self, event: str, data: Any = None) -> int:
        """
        Call all live listeners registered for *event* with *data*.
        Returns the number of listeners that were called.
        """
        listeners = self._listeners.get(event)
        if not listeners:
            return 0
        called = 0
        for key, listener in list(listeners.items()):
            if listener.call(data):
                called += 1
            else:
                del listeners[key]
        return called

    def listener_count(self, event: str) -> int:
        """Return the number of live listeners for *event*."""
        listeners = self._listeners.get(event)
        if not listeners:
            return 0
        count = 0
        for key, listener in list(listeners.items()):
            if listener.is_alive():
                count += 1
            else:
                del listeners[key]
        return count
