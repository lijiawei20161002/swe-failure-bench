"""
JSON-RPC 2.0 dispatcher.

Routes method calls to registered Python functions and returns
properly-formed response dicts.

BUG B: Notifications (requests without an `id`) must be processed but must
return None — the caller should not send any response. Currently the
dispatcher raises an exception when it encounters a notification because
it tries to look up `msg["id"]` which doesn't exist.
"""

from __future__ import annotations

import traceback
from typing import Any, Callable

from protocol import (
    JsonRpcError,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    INTERNAL_ERROR,
    is_notification,
    make_response,
    make_error_response,
    validate_request,
)


class Dispatcher:
    def __init__(self):
        self._methods: dict[str, Callable] = {}

    def register(self, name: str, fn: Callable) -> None:
        self._methods[name] = fn

    def method(self, name: str | None = None):
        """Decorator: @dispatcher.method() or @dispatcher.method('custom_name')"""
        def decorator(fn: Callable) -> Callable:
            self.register(name or fn.__name__, fn)
            return fn
        return decorator

    def dispatch(self, msg: dict) -> dict | None:
        """
        Process a single validated request dict.
        Returns a response dict, or None if *msg* is a notification.

        BUG B: if msg has no 'id' (notification), we should return None early.
        Currently we don't check — the code below reaches `msg["id"]` and
        raises KeyError, which propagates up instead of being silently ignored.
        """
        validate_request(msg)

        # BUG B: Missing early return for notifications.
        # Fix should be:
        #   if is_notification(msg):
        #       self._call(msg["method"], msg.get("params"))
        #       return None

        req_id = msg["id"]   # BUG B: KeyError if notification (no "id")
        method_name = msg["method"]
        params = msg.get("params")

        try:
            result = self._call(method_name, params)
            return make_response(req_id, result)
        except JsonRpcError as e:
            return make_error_response(req_id, e)
        except Exception as e:
            err = JsonRpcError(INTERNAL_ERROR, str(e), traceback.format_exc())
            return make_error_response(req_id, err)

    def dispatch_batch(self, messages: list[dict]) -> list[dict]:
        """
        Process a batch of requests. Returns list of non-None responses.
        Responses must appear in the same order as the requests that generated them.
        Notifications produce no response and are excluded from the output list.
        """
        responses = []
        for msg in messages:
            resp = self.dispatch(msg)
            if resp is not None:
                responses.append(resp)
        return responses

    def _call(self, method_name: str, params: Any) -> Any:
        if method_name not in self._methods:
            raise JsonRpcError(METHOD_NOT_FOUND, f"Method not found: {method_name}")
        fn = self._methods[method_name]
        if params is None:
            return fn()
        if isinstance(params, list):
            return fn(*params)
        if isinstance(params, dict):
            return fn(**params)
        raise JsonRpcError(INVALID_REQUEST, "params must be array or object")
