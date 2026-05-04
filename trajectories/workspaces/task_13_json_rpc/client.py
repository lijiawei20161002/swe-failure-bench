"""
JSON-RPC 2.0 client-side batch response matching.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BatchResult:
    """Holds matched results and errors for a batch of requests."""
    results: dict[Any, Any] = field(default_factory=dict)   # id → result
    errors:  dict[Any, Any] = field(default_factory=dict)   # id → error dict


def match_batch_responses(
    requests: list[dict],
    responses: list[dict],
) -> BatchResult:
    """
    Match a list of server responses to the originating requests by id.

    Notifications (requests without 'id') must be skipped — they produce no
    server response.
    """
    resp_by_id = {}
    for r in responses:
        rid = r.get("id")
        if rid is not None:
            resp_by_id[rid] = r

    out = BatchResult()
    for req in requests:
        req_id = req.get("id")
        if req_id is None:
            continue
        resp = resp_by_id.get(req_id)
        if resp is None:
            continue
        if "result" in resp:
            out.results[req_id] = resp["result"]
        elif "error" in resp:
            out.errors[req_id] = resp["error"]
    return out


# ── correct reference implementation (for comparison) ────────────────────────

def match_batch_responses_correct(
    requests: list[dict],
    responses: list[dict],
) -> BatchResult:
    """Reference: match by id (not used, just for illustration)."""
    resp_by_id = {}
    for r in responses:
        rid = r.get("id")
        if rid is not None:
            resp_by_id[rid] = r

    out = BatchResult()
    for req in requests:
        req_id = req.get("id")
        if req_id is None:
            continue
        resp = resp_by_id.get(req_id)
        if resp is None:
            continue
        if "result" in resp:
            out.results[req_id] = resp["result"]
        elif "error" in resp:
            out.errors[req_id] = resp["error"]
    return out
