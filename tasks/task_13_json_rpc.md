# Task: Fix JSON-RPC 2.0 Implementation

## User Persona

- **High-level goals:** Building a JSON-RPC 2.0 server/client. Has read the spec at jsonrpc.org carefully. Will check error codes against the spec table.
- **Familiarity with tools:** Has implemented REST APIs before. Understands the difference between a Request (has id) and a Notification (no id). Knows batch semantics.
- **Communication style:** Quotes the spec: "Section 5.1 says Parse error is -32700, but you have -32600."
- **Patience style:** One issue per milestone. Won't accept partial fixes.
- **Hint policy:** Will quote the spec section, not the line number in code.

## Context

Three files: `protocol.py`, `dispatcher.py`, `client.py`. Tests: `tests/test_jsonrpc.py`.

```bash
cd /workspace && pip install pytest --quiet && pytest tests/ -x -q 2>&1 | tail -30
```

## Milestones

### Milestone 1: Fix Error Codes in protocol.py

**Initial Prompt:**

> "Your error codes are wrong. JSON-RPC 2.0 spec §5.1: Parse error = -32700, Invalid Request = -32600. They're swapped in `protocol.py`. Fix them and make sure the tests pass — the tests check both the constants and the exceptions raised."

**Planned Interactions:**

- Clarification answers:
  - If agent asks about other codes: "METHOD_NOT_FOUND (-32601), INVALID_PARAMS (-32602), and INTERNAL_ERROR (-32603) are correct. Only Parse error and Invalid Request are swapped."
- Corrections and hints:
  - If agent changes constants but parse error is raised with wrong code: "The `parse_message()` function raises a JsonRpcError for bad JSON — make sure it uses `PARSE_ERROR` which is now -32700."

**Completion Criteria:**

`pytest tests/test_jsonrpc.py::TestErrorCodes -x -q` passes all tests.

---

### Milestone 2: Fix Notification Handling in dispatcher.py

**Initial Prompt:**

> "When I dispatch a notification (a message with no `id`), the dispatcher raises a `KeyError` instead of processing the method and returning `None`. Notifications must be handled silently — call the method, return None, send no response. Fix `dispatcher.py`."

**Planned Interactions:**

- Clarification answers:
  - If agent asks what to return: "For a notification: call the method (fire-and-forget), return None. For a batch: exclude notification responses from the output list."
  - If agent asks about errors in notification handlers: "If the notification handler raises, swallow the exception — notifications get no error response either."
- Corrections and hints:
  - If dispatch returns None but handler isn't called: "The test `test_notification_still_calls_handler` checks that the handler fires even though there's no response."

**Completion Criteria:**

`pytest tests/test_jsonrpc.py::TestDispatcherSingle tests/test_jsonrpc.py::TestDispatcherBatch -x -q` passes.

---

### Milestone 3: Fix Batch Response Matching in client.py

**Initial Prompt:**

> "The client's `match_batch_responses()` uses positional matching (zip) instead of id-based matching. When a batch contains notifications, the server returns fewer responses, shifting the zip alignment. Fix it to match by `id`."

**Planned Interactions:**

- Clarification answers:
  - If agent asks about the expected behavior: "Build a dict from responses keyed by `id`. Then for each request that has an `id`, look it up in the dict. Skip notifications (no id = no response)."
- Corrections and hints:
  - If agent fixes notification skipping but reorder still fails: "The server may return responses in any order — you must match by id, not position."

**Completion Criteria:**

`pytest tests/ -x -q` passes all tests.
