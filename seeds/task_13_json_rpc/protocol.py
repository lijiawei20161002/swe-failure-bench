"""
JSON-RPC 2.0 protocol layer.

Spec: https://www.jsonrpc.org/specification

Message types:
  Request      { jsonrpc, id, method, params? }
  Notification { jsonrpc, method, params? }       ← id is absent
  Response     { jsonrpc, id, result }             ← success
  Error        { jsonrpc, id, error: {code, message, data?} }
  Batch        [ Request | Notification, ... ]

Standard error codes:
  -32700  Parse error
  -32600  Invalid Request
  -32601  Method not found
  -32602  Invalid params
  -32603  Internal error
  -32000 to -32099  Server error (reserved)

BUG A: PARSE_ERROR and INVALID_REQUEST codes are swapped.
  Current: PARSE_ERROR = -32600, INVALID_REQUEST = -32700
  Correct: PARSE_ERROR = -32700, INVALID_REQUEST = -32600
"""

from __future__ import annotations

import json
from typing import Any


# ── error codes ───────────────────────────────────────────────────────────────

PARSE_ERROR       = -32600   # BUG A: should be -32700
INVALID_REQUEST   = -32700   # BUG A: should be -32600
METHOD_NOT_FOUND  = -32601
INVALID_PARAMS    = -32602
INTERNAL_ERROR    = -32603
SERVER_ERROR_MIN  = -32099
SERVER_ERROR_MAX  = -32000


class JsonRpcError(Exception):
    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def to_dict(self) -> dict:
        d = {"code": self.code, "message": self.message}
        if self.data is not None:
            d["data"] = self.data
        return d


# ── message constructors ──────────────────────────────────────────────────────

def make_request(method: str, params=None, id=1) -> dict:
    msg = {"jsonrpc": "2.0", "method": method, "id": id}
    if params is not None:
        msg["params"] = params
    return msg


def make_notification(method: str, params=None) -> dict:
    msg = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    return msg


def make_response(id, result) -> dict:
    return {"jsonrpc": "2.0", "id": id, "result": result}


def make_error_response(id, error: JsonRpcError) -> dict:
    return {"jsonrpc": "2.0", "id": id, "error": error.to_dict()}


# ── parsing / validation ──────────────────────────────────────────────────────

def parse_message(raw: str) -> list[dict] | dict:
    """
    Parse raw JSON string into one or more request dicts.
    Returns a list for batch requests, a single dict otherwise.
    Raises JsonRpcError for malformed JSON or invalid structure.
    """
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        raise JsonRpcError(PARSE_ERROR, f"Parse error: {e}")

    if isinstance(obj, list):
        if not obj:
            raise JsonRpcError(INVALID_REQUEST, "Batch must not be empty")
        return obj
    return obj


def validate_request(msg: dict) -> None:
    """Raise JsonRpcError if *msg* is not a valid JSON-RPC 2.0 request."""
    if not isinstance(msg, dict):
        raise JsonRpcError(INVALID_REQUEST, "Request must be an object")
    if msg.get("jsonrpc") != "2.0":
        raise JsonRpcError(INVALID_REQUEST, 'jsonrpc must be "2.0"')
    if "method" not in msg or not isinstance(msg["method"], str):
        raise JsonRpcError(INVALID_REQUEST, "method must be a string")


def is_notification(msg: dict) -> bool:
    return "id" not in msg
