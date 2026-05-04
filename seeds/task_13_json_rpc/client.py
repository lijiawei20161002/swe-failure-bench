"""
JSON-RPC 2.0 client-side batch response matching.

BUG C: When sending a batch of requests, the server returns responses in any
order (or omits responses for notifications). The client must match responses
to requests by id, not by position. Currently the client zips requests and
responses by position, which is wrong when:
  - the batch contains notifications (no response → index shift)
  - the server reorders responses
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

    BUG C: instead of matching by id, the code uses positional zip, which
    shifts results when notifications are present in the batch.
    """
    out = BatchResult()

    # BUG C: positional zip instead of id-based matching
    for req, resp in zip(requests, responses):           # BUG C
        req_id = req.get("id")
        if req_id is None:
            continue   # notification — but BUG C already misaligned things
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
