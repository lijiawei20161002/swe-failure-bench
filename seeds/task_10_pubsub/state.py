"""
State builder: reconstructs current state by replaying events.

Provides a snapshot() method that the broker uses to take an atomic
point-in-time view of the current state.
"""
from __future__ import annotations
from broker import Event


class StateBuilder:
    """
    Maintains a key-value state by replaying 'set' and 'delete' events.
    """

    def __init__(self):
        self._state: dict = {}

    def apply(self, event: Event) -> None:
        """Apply a single event to update in-memory state."""
        payload = event.payload
        if payload.get("op") == "set":
            self._state[payload["key"]] = payload["value"]
        elif payload.get("op") == "delete":
            self._state.pop(payload["key"], None)

    def snapshot(self, log: list[Event]) -> dict:
        """
        Replay all events in *log* and return the resulting state dict.
        Called by the broker to take a point-in-time snapshot.
        """
        state: dict = {}
        for event in log:
            payload = event.payload
            if payload.get("op") == "set":
                state[payload["key"]] = payload["value"]
            elif payload.get("op") == "delete":
                state.pop(payload["key"], None)
        return state

    def get(self, key: str):
        return self._state.get(key)


def make_set_event(key: str, value) -> dict:
    return {"op": "set", "key": key, "value": value}


def make_delete_event(key: str) -> dict:
    return {"op": "delete", "key": key}
