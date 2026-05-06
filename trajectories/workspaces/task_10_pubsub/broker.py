"""
Event broker: routes published events to registered subscribers.

The broker maintains a global event log (append-only sequence of events).
Subscribers register with an *offset* — they receive all events from that
offset onward.  This allows a new subscriber to:

  1. Take a snapshot of current state at offset N.
  2. Register with offset N.
  3. Receive all events from N onwards, keeping state in sync.

The critical invariant:
  The snapshot must be taken WHILE holding the broker lock (or equivalent),
  so that no new events can be published between the snapshot and the
  subscription registration.  If events can arrive between snapshot time
  and subscription time, those events are missed — the subscriber starts
  receiving from the subscription offset, which is AFTER those events.

Usage:
    broker = Broker()
    broker.publish("user.created", {"id": 1})
    broker.publish("user.updated", {"id": 1, "name": "Alice"})

    # safe subscription (takes snapshot atomically with registration)
    sub = broker.subscribe_from_snapshot()

    broker.publish("user.deleted", {"id": 1})
    events = sub.drain()   # should get all 3 events
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Event:
    offset: int
    topic: str
    payload: Any


class Subscription:
    def __init__(self, log: list[Event], start_offset: int):
        self._log = log
        self._cursor = start_offset

    def drain(self) -> list[Event]:
        """Return all events from cursor onward and advance cursor."""
        events = [e for e in self._log if e.offset >= self._cursor]
        if events:
            self._cursor = events[-1].offset + 1
        return events


class Broker:
    def __init__(self):
        self._log: list[Event] = []
        self._offset: int = 0
        self._lock = threading.Lock()

    def publish(self, topic: str, payload: Any) -> Event:
        with self._lock:
            evt = Event(offset=self._offset, topic=topic, payload=payload)
            self._log.append(evt)
            self._offset += 1
            return evt

    def current_offset(self) -> int:
        """Return the offset of the NEXT event to be published."""
        with self._lock:
            return self._offset

    def subscribe_from_offset(self, offset: int) -> Subscription:
        """Subscribe to all events with offset >= *offset*."""
        return Subscription(self._log, offset)

    def subscribe_from_snapshot(self, state_builder: "StateBuilder") -> tuple["Subscription", dict]:
        """
        Atomically take a snapshot of current state and register a
        subscription starting from the snapshot offset.

        Returns (subscription, snapshot_state).
        """
        with self._lock:
            # Capture the log and offset atomically so no event can slip
            # through the gap between the snapshot and the subscription.
            log_snapshot = list(self._log)
            offset = self._offset
        snapshot = state_builder.snapshot(log_snapshot)
        return self.subscribe_from_offset(offset), snapshot
