"""
Tests for EventBus.
Run: pip install pytest && pytest tests/ -x -q
"""
import gc
import weakref
import pytest
from event_bus import EventBus


class TestBasicEmit:
    """Sanity: plain (non-method) callables must work."""

    def test_lambda_callback(self):
        bus = EventBus()
        results = []
        cb = lambda data: results.append(data)
        bus.subscribe("x", cb)
        bus.emit("x", 42)
        assert results == [42]

    def test_plain_function_callback(self):
        bus = EventBus()
        log = []

        def handler(data):
            log.append(data)

        bus.subscribe("ev", handler)
        bus.emit("ev", "hello")
        assert log == ["hello"]

    def test_no_listeners(self):
        bus = EventBus()
        count = bus.emit("nothing")
        assert count == 0

    def test_emit_returns_count(self):
        bus = EventBus()
        results = []
        cb1 = lambda d: results.append(("a", d))
        cb2 = lambda d: results.append(("b", d))
        bus.subscribe("ev", cb1)
        bus.subscribe("ev", cb2)
        n = bus.emit("ev", 1)
        assert n == 2

    def test_unsubscribe(self):
        bus = EventBus()
        calls = []
        cb = lambda d: calls.append(d)
        bus.subscribe("ev", cb)
        bus.unsubscribe("ev", cb)
        bus.emit("ev", "data")
        assert calls == []

    def test_multiple_events(self):
        bus = EventBus()
        a_log, b_log = [], []
        ca = lambda d: a_log.append(d)
        cb = lambda d: b_log.append(d)
        bus.subscribe("a", ca)
        bus.subscribe("b", cb)
        bus.emit("a", 1)
        bus.emit("b", 2)
        assert a_log == [1] and b_log == [2]


class TestBoundMethodSubscription:
    """
    Core correctness: subscribing a bound method must work.

    The bug: EventBus stores callbacks in a WeakValueDictionary.
    A bound method (e.g. `obj.handler`) is an ephemeral object — it is
    created fresh on each attribute access and has no persistent strong
    reference.  Storing it under a weak reference means it is eligible for
    immediate GC, so the subscription is silently lost before emit() is ever
    called.

    Fix: use strong references for the callbacks themselves, implementing
    weak-subscriber semantics via weakref.WeakMethod or by storing
    (weakref(obj), method_name) pairs instead of bound-method objects.
    """

    def test_method_callback_is_called(self):
        """The most basic case: subscribe a bound method and emit."""
        bus = EventBus()
        received = []

        class Listener:
            def handle(self, data):
                received.append(data)

        listener = Listener()
        bus.subscribe("event", listener.handle)
        bus.emit("event", "payload")

        assert received == ["payload"], (
            "Bound method callback was never called. "
            "EventBus is storing the bound method in a WeakValueDictionary. "
            "Bound methods are ephemeral objects with no other strong reference, "
            "so they are immediately garbage-collected after subscribe() returns. "
            "Fix: store strong references to callbacks, or use weakref.WeakMethod."
        )

    def test_method_callback_called_multiple_times(self):
        bus = EventBus()
        calls = []

        class Counter:
            def tick(self, data):
                calls.append(data)

        c = Counter()
        bus.subscribe("tick", c.tick)
        for i in range(5):
            bus.emit("tick", i)

        assert calls == [0, 1, 2, 3, 4]

    def test_multiple_method_subscribers(self):
        bus = EventBus()
        log = []

        class A:
            def on_event(self, data):
                log.append(("A", data))

        class B:
            def on_event(self, data):
                log.append(("B", data))

        a, b = A(), B()
        bus.subscribe("ev", a.on_event)
        bus.subscribe("ev", b.on_event)
        bus.emit("ev", 99)

        assert ("A", 99) in log
        assert ("B", 99) in log

    def test_listener_count_with_method(self):
        bus = EventBus()

        class H:
            def handle(self, d): pass

        h = H()
        bus.subscribe("e", h.handle)
        assert bus.listener_count("e") == 1, (
            "listener_count should be 1 after subscribing a bound method. "
            "If it is 0, the bound method was already GC'd."
        )

    def test_subscriber_collected_removes_subscription(self):
        """
        Once the subscriber object is deleted, the subscription should
        be automatically removed (the whole point of weak references).
        """
        bus = EventBus()
        calls = []

        class Temp:
            def handle(self, data):
                calls.append(data)

        t = Temp()
        # To make weak-subscriber semantics work correctly we need the
        # bus to hold a WeakMethod or (weakref, name) pair.
        # For this test: after del t and GC, no more calls.
        bus.subscribe("ev", t.handle)
        bus.emit("ev", "before")
        del t
        gc.collect()
        bus.emit("ev", "after")

        # First emit must have reached the handler
        assert "before" in calls, "handler must be called while subscriber is alive"
        # Second emit must not reach the handler (subscriber gone)
        assert "after" not in calls, (
            "handler was called after subscriber was deleted. "
            "The bus should not hold a strong reference to the subscriber."
        )

    def test_mixed_callbacks(self):
        """Both plain functions and bound methods must work together."""
        bus = EventBus()
        log = []

        def plain(data):
            log.append(("plain", data))

        class H:
            def method(self, data):
                log.append(("method", data))

        h = H()
        bus.subscribe("ev", plain)
        bus.subscribe("ev", h.method)
        bus.emit("ev", 7)

        assert ("plain", 7) in log
        assert ("method", 7) in log
