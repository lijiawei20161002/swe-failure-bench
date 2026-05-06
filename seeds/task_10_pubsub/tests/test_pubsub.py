"""
Tests for the pub/sub replica system.
Run: pip install pytest && pytest tests/ -x -q
"""
import threading
import time
import pytest
from broker import Broker
from state import StateBuilder, make_set_event, make_delete_event
from replica import Replica


class TestBrokerBasics:
    def test_publish_and_subscribe(self):
        b = Broker()
        b.publish("t", make_set_event("k", "v"))
        sub = b.subscribe_from_offset(0)
        events = sub.drain()
        assert len(events) == 1
        assert events[0].payload["key"] == "k"

    def test_subscribe_from_offset_skips_old(self):
        b = Broker()
        b.publish("t", make_set_event("a", 1))
        b.publish("t", make_set_event("b", 2))
        sub = b.subscribe_from_offset(1)   # start at offset 1
        events = sub.drain()
        assert len(events) == 1
        assert events[0].payload["key"] == "b"

    def test_drain_advances_cursor(self):
        b = Broker()
        b.publish("t", make_set_event("x", 1))
        sub = b.subscribe_from_offset(0)
        sub.drain()
        # Nothing new
        assert sub.drain() == []
        # Publish more
        b.publish("t", make_set_event("y", 2))
        events = sub.drain()
        assert len(events) == 1


class TestSnapshotAndSubscribe:
    """
    Core correctness: subscribe_from_snapshot() must be atomic.

    Pattern:
      1. Publish some events (history)
      2. Call subscribe_from_snapshot()  ← must be atomic
      3. Publish more events (future)
      4. Merge snapshot + future events → complete state

    The subscription offset returned by subscribe_from_snapshot() must
    exactly match the snapshot's watermark: events with offset < watermark
    are captured in the snapshot; events with offset >= watermark arrive
    via the subscription.

    BUG: subscribe_from_snapshot() calls state_builder.snapshot() and
    current_offset() in TWO separate steps, without holding the lock.
    Any event published between those two calls is:
      - NOT in the snapshot (snapshot was taken before it)
      - NOT in the subscription (subscription starts after it)
      → The event is silently missed.

    Fix: hold self._lock across both calls in subscribe_from_snapshot()
    so no event can slip through the gap.
    """

    def test_replica_sees_pre_snapshot_events_in_state(self):
        """State before snapshot must appear in replica after start()."""
        broker = Broker()
        broker.publish("t", make_set_event("a", 1))
        broker.publish("t", make_set_event("b", 2))

        replica = Replica(broker)
        replica.start()   # snapshot captures a=1, b=2

        assert replica.get("a") == 1
        assert replica.get("b") == 2

    def test_replica_sees_post_snapshot_events_after_sync(self):
        """Events published after start() arrive via subscription."""
        broker = Broker()
        broker.publish("t", make_set_event("x", 10))

        replica = Replica(broker)
        replica.start()

        broker.publish("t", make_set_event("y", 20))
        replica.sync()

        assert replica.get("x") == 10
        assert replica.get("y") == 20

    def test_no_event_missed_between_snapshot_and_subscription(self):
        """
        Events published between snapshot() and subscribe_from_offset()
        inside subscribe_from_snapshot() must NOT be missed.

        This test simulates the race by injecting an event between the
        snapshot call and the offset capture using a subclass that
        publishes an event mid-snapshot.

        Without the fix, the injected event is absent from both the
        snapshot state and the subscription → replica never sees it.
        """
        broker = Broker()
        broker.publish("t", make_set_event("before", 1))

        # Subclass StateBuilder to inject an event during snapshot()
        injected = []

        class InjectingBuilder(StateBuilder):
            def snapshot(self, log):
                result = super().snapshot(log)
                # Simulate an event published after snapshot but before
                # subscribe_from_offset() is called
                evt = broker.publish("t", make_set_event("injected", 99))
                injected.append(evt)
                return result

        builder = InjectingBuilder()
        sub, snapshot_state = broker.subscribe_from_snapshot(builder)

        # Deliver everything the subscription knows about
        replica_state = dict(snapshot_state)
        for evt in sub.drain():
            p = evt.payload
            if p.get("op") == "set":
                replica_state[p["key"]] = p["value"]
            elif p.get("op") == "delete":
                replica_state.pop(p["key"], None)

        assert "injected" in replica_state, (
            "The event published between snapshot() and subscribe_from_offset() "
            "was missed. subscribe_from_snapshot() is not atomic: the snapshot "
            "was taken before the injected event arrived, so it's not in the "
            "snapshot state; then subscribe_from_offset() was called after, so "
            "the injected event's offset is before the subscription start. "
            "Fix: hold self._lock across both the snapshot call and the "
            "current_offset() capture in subscribe_from_snapshot()."
        )
        assert replica_state["before"] == 1
        assert replica_state["injected"] == 99

    def test_replica_full_sync_no_missed_events(self):
        """
        Replica must converge to exactly the broker's state, no gaps.
        Uses the injecting builder to force the race condition.
        """
        broker = Broker()
        broker.publish("t", make_set_event("a", 1))
        broker.publish("t", make_set_event("b", 2))

        class InjectingBuilder(StateBuilder):
            def snapshot(self, log):
                result = super().snapshot(log)
                broker.publish("t", make_set_event("c", 3))  # injected mid-gap
                return result

        replica = Replica(broker)
        # Temporarily patch broker to use injecting builder
        original = broker.subscribe_from_snapshot

        def patched(builder):
            return original(InjectingBuilder())

        broker.subscribe_from_snapshot = patched
        replica.start()
        replica.sync()

        # broker has a=1, b=2, c=3 — replica must too
        assert replica.get("a") == 1
        assert replica.get("b") == 2
        assert replica.get("c") == 3, (
            f"replica.get('c') = {replica.get('c')!r}, expected 3. "
            "Event 'c' was published during the snapshot/subscribe gap "
            "and was silently missed."
        )

    def test_no_duplicate_events(self):
        """Events must not be applied twice (once in snapshot, once in sub)."""
        broker = Broker()
        broker.publish("t", make_set_event("counter", 0))

        # Accumulator that counts how many times each key was set
        set_counts: dict[str, int] = {}

        class CountingBuilder(StateBuilder):
            def snapshot(self, log):
                for e in log:
                    if e.payload.get("op") == "set":
                        k = e.payload["key"]
                        set_counts[k] = set_counts.get(k, 0) + 1
                return super().snapshot(log)

        sub, snap = broker.subscribe_from_snapshot(CountingBuilder())
        for evt in sub.drain():
            if evt.payload.get("op") == "set":
                k = evt.payload["key"]
                set_counts[k] = set_counts.get(k, 0) + 1

        assert set_counts.get("counter", 0) == 1, (
            f"'counter' was applied {set_counts.get('counter', 0)} time(s), "
            "expected exactly 1. An event appeared in both the snapshot and "
            "the subscription."
        )
