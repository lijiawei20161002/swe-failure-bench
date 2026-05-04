"""Tests for JSON-RPC 2.0 implementation. Run: pytest tests/ -x"""
import json
import pytest
from protocol import (
    PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INTERNAL_ERROR,
    JsonRpcError, make_request, make_notification, parse_message,
    is_notification,
)
from dispatcher import Dispatcher
from client import match_batch_responses, BatchResult


# ── protocol — error codes ────────────────────────────────────────────────────

class TestErrorCodes:
    def test_parse_error_code(self):
        """JSON-RPC spec §5.1: Parse error is -32700."""
        assert PARSE_ERROR == -32700, (
            f"PARSE_ERROR must be -32700 per JSON-RPC spec, got {PARSE_ERROR}"
        )

    def test_invalid_request_code(self):
        """JSON-RPC spec §5.1: Invalid Request is -32600."""
        assert INVALID_REQUEST == -32600, (
            f"INVALID_REQUEST must be -32600, got {INVALID_REQUEST}"
        )

    def test_method_not_found_code(self):
        assert METHOD_NOT_FOUND == -32601

    def test_internal_error_code(self):
        assert INTERNAL_ERROR == -32603

    def test_parse_error_raised_on_bad_json(self):
        with pytest.raises(JsonRpcError) as exc_info:
            parse_message("{bad json")
        assert exc_info.value.code == -32700, (
            f"Bad JSON must raise code -32700 (Parse error), got {exc_info.value.code}"
        )

    def test_invalid_request_raised_on_empty_batch(self):
        with pytest.raises(JsonRpcError) as exc_info:
            parse_message("[]")
        assert exc_info.value.code == -32600, (
            f"Empty batch must raise -32600 (Invalid Request), got {exc_info.value.code}"
        )


# ── protocol — message construction ──────────────────────────────────────────

class TestMessages:
    def test_is_notification_true(self):
        n = make_notification("ping")
        assert is_notification(n) is True

    def test_is_notification_false(self):
        r = make_request("ping", id=1)
        assert is_notification(r) is False

    def test_make_request_has_id(self):
        r = make_request("add", [1, 2], id=42)
        assert r["id"] == 42
        assert r["method"] == "add"

    def test_notification_has_no_id(self):
        n = make_notification("log", {"msg": "hello"})
        assert "id" not in n


# ── dispatcher — single request ───────────────────────────────────────────────

class TestDispatcherSingle:
    def setup_method(self):
        self.d = Dispatcher()
        self.d.register("add", lambda a, b: a + b)
        self.d.register("echo", lambda msg: msg)

    def test_dispatch_returns_result(self):
        req = make_request("add", [3, 4], id=1)
        resp = self.d.dispatch(req)
        assert resp["result"] == 7
        assert resp["id"] == 1

    def test_dispatch_method_not_found(self):
        req = make_request("missing", id=2)
        resp = self.d.dispatch(req)
        assert "error" in resp
        assert resp["error"]["code"] == METHOD_NOT_FOUND

    def test_dispatch_with_kwargs(self):
        req = make_request("add", {"a": 10, "b": 20}, id=3)
        resp = self.d.dispatch(req)
        assert resp["result"] == 30

    def test_dispatch_notification_returns_none(self):
        """
        A notification (no id) must be processed but produce NO response (None).
        The dispatcher must not raise and must not return a response dict.
        """
        notification = make_notification("echo", ["fired"])
        result = self.d.dispatch(notification)
        assert result is None, (
            f"Notification must return None, got {result!r}"
        )

    def test_notification_still_calls_handler(self):
        """The handler for a notification must still be invoked."""
        calls = []
        self.d.register("track", lambda: calls.append(True))
        self.d.dispatch(make_notification("track"))
        assert len(calls) == 1, "Notification handler must be called"


# ── dispatcher — batch ────────────────────────────────────────────────────────

class TestDispatcherBatch:
    def setup_method(self):
        self.d = Dispatcher()
        self.d.register("double", lambda x: x * 2)
        self.d.register("notify_log", lambda msg: None)

    def test_batch_responses_match_requests(self):
        reqs = [make_request("double", [1], id=1),
                make_request("double", [2], id=2)]
        resps = self.d.dispatch_batch(reqs)
        assert len(resps) == 2
        assert any(r["result"] == 2 for r in resps)
        assert any(r["result"] == 4 for r in resps)

    def test_batch_excludes_notification_responses(self):
        """Notifications in a batch must not produce a response entry."""
        reqs = [
            make_request("double", [5], id=10),
            make_notification("notify_log", ["hello"]),
            make_request("double", [6], id=11),
        ]
        resps = self.d.dispatch_batch(reqs)
        assert len(resps) == 2, (
            f"Batch with 1 notification should produce 2 responses, got {len(resps)}"
        )
        ids = {r["id"] for r in resps}
        assert ids == {10, 11}


# ── client — batch response matching ─────────────────────────────────────────

class TestClientMatching:
    def test_simple_match(self):
        requests  = [make_request("a", id=1), make_request("b", id=2)]
        responses = [{"jsonrpc":"2.0","id":1,"result":"A"},
                     {"jsonrpc":"2.0","id":2,"result":"B"}]
        out = match_batch_responses(requests, responses)
        assert out.results == {1: "A", 2: "B"}

    def test_match_with_notification_in_batch(self):
        """
        When a notification is in the batch, its id=None response is absent.
        The client must still correctly match the remaining responses by id,
        NOT by position.
        """
        requests = [
            make_request("a", id=1),
            make_notification("log"),     # no response
            make_request("b", id=2),
        ]
        # Server returns 2 responses for 2 non-notification requests
        responses = [
            {"jsonrpc": "2.0", "id": 2, "result": "B"},   # note: server may reorder
            {"jsonrpc": "2.0", "id": 1, "result": "A"},
        ]
        out = match_batch_responses(requests, responses)
        assert out.results.get(1) == "A", (
            f"Request id=1 should map to 'A', got {out.results.get(1)!r}"
        )
        assert out.results.get(2) == "B", (
            f"Request id=2 should map to 'B', got {out.results.get(2)!r}"
        )

    def test_match_reordered_responses(self):
        """Server may return batch responses in any order — client must match by id."""
        requests  = [make_request("x", id=10), make_request("y", id=20)]
        responses = [{"jsonrpc":"2.0","id":20,"result":"Y"},
                     {"jsonrpc":"2.0","id":10,"result":"X"}]
        out = match_batch_responses(requests, responses)
        assert out.results[10] == "X"
        assert out.results[20] == "Y"

    def test_match_error_response(self):
        requests  = [make_request("bad", id=99)]
        responses = [{"jsonrpc":"2.0","id":99,
                      "error":{"code":-32601,"message":"Method not found"}}]
        out = match_batch_responses(requests, responses)
        assert 99 in out.errors
        assert out.results.get(99) is None
