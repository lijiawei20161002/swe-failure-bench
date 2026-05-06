"""
Replica: a read replica that stays in sync with the broker via subscription.

The replica starts by taking a consistent snapshot of current state, then
processes all subsequent events to stay up-to-date.  This is the standard
"change data capture" pattern used by read replicas, caches, and search
indexes.

The invariant: after calling sync(), the replica's state must match the
primary's state for all events that existed at or before the snapshot,
PLUS all events published after subscription registration.  No event
must be missed or applied twice.
"""
from __future__ import annotations

from broker import Broker, Subscription
from state import StateBuilder, make_set_event, make_delete_event


class Replica:
    """
    Read replica that subscribes to the broker and applies events.
    """

    def __init__(self, broker: Broker):
        self._broker = broker
        self._state: dict = {}
        self._sub: Subscription | None = None

    def start(self) -> None:
        """
        Initialize the replica by taking a snapshot + subscribing.

        After start(), call sync() to process new events.
        """
        builder = StateBuilder()
        self._sub, self._state = self._broker.subscribe_from_snapshot(builder)

    def sync(self) -> int:
        """
        Apply all pending events from the subscription.
        Returns the number of events processed.
        """
        if self._sub is None:
            raise RuntimeError("Call start() before sync()")
        events = self._sub.drain()
        for evt in events:
            payload = evt.payload
            if payload.get("op") == "set":
                self._state[payload["key"]] = payload["value"]
            elif payload.get("op") == "delete":
                self._state.pop(payload["key"], None)
        return len(events)

    def get(self, key: str):
        return self._state.get(key)

    @property
    def state(self) -> dict:
        return dict(self._state)
