# Task: Fix Redis RESP Protocol Parser

## User Persona

- **High-level goals:** Building a Redis client library from scratch. The RESP parser is the core component — must handle all Redis reply types, incremental feeding (streaming), and pipelining.
- **Familiarity with tools:** Has read the RESP spec (redis.io/docs/reference/protocol-spec). Knows Redis well as a user. Writing the parser from scratch for a client that competes with redis-py.
- **Communication style:** Sends raw RESP bytes and expected parsed output side-by-side. Knows exactly when a \r\n is missing.
- **Patience style:** Will catch every byte-offset bug. Expects the parser to handle any RESP input the Redis server can produce.
- **Hint policy:** Will paste the relevant line from the RESP spec if the parsing logic is wrong.

## Context

Implementation: `resp_parser.py`. Tests: `tests/test_resp_parser.py`.

```bash
cd /workspace && pip install pytest --quiet && pytest tests/ -x -q 2>&1 | tail -30
```

## Milestones

### Milestone 1: Fix Bulk String Parsing (Missing CRLF Consumption)

**Initial Prompt:**

> "The RESP parser in `resp_parser.py` fails when two bulk strings are sent back-to-back. After reading a bulk string's data, it's not consuming the trailing `\\r\\n`, so the next parse starts at the wrong offset. Fix the `$` case in `_parse_one()`. The test `test_two_consecutive_bulk_strings` shows it."

**Planned Interactions:**

- Clarification answers:
  - If agent asks about the RESP bulk string format: "It's `$<len>\\r\\n<data>\\r\\n`. After reading `<len>` bytes of data, you must consume two more bytes for the trailing CRLF."
- Corrections and hints:
  - If agent adds `pos += 2` but `test_bulk_string_containing_crlf` fails: "You can't scan for `\\r\\n` in the data — you must use the declared length. The data itself can contain `\\r\\n`."
  - If agent checks `pos + length + 2 > len(buf)` for incomplete detection: "Good — check for both the data AND the trailing CRLF before returning."

**Completion Criteria:**

`pytest tests/test_resp_parser.py::TestBulkStrings -x -q` passes all 6 tests.

---

### Milestone 2: Fix Array Parsing (Elements Parsed from Wrong Offset)

**Initial Prompt:**

> "Arrays are broken — `*3\\r\\n$3\\r\\nSET\\r\\n$3\\r\\nkey\\r\\n$5\\r\\nvalue\\r\\n` returns `[b'SET', b'SET', b'SET']` instead of `[b'SET', b'key', b'value']`. Each element is being re-parsed from the same offset. Fix the `*` case in `_parse_one()` so each element is parsed at the correct position after the previous one."

**Planned Interactions:**

- Corrections and hints:
  - If agent fixes the position but nested arrays break: "Make sure you thread `pos` through the recursive call correctly — `_parse_one(buf, pos)` returns `(value, new_pos)` and you must use `new_pos` for the next element."

**Completion Criteria:**

`pytest tests/test_resp_parser.py::TestArrays -x -q` passes all 6 tests.

---

### Milestone 3: Streaming, Pipelining, and Error Handling

**Initial Prompt:**

> "Now run the full test suite. Remaining failures are likely in `TestStreaming` (feeding in chunks, pipelining multiple commands) and `TestErrorHandling` (invalid type bytes, negative bulk lengths other than -1). Fix all remaining issues."

**Planned Interactions:**

- Clarification answers:
  - If agent asks about pipelining: "Multiple complete RESP messages in one `feed()` call — all of them should be parsed and available via successive `get_message()` calls."
  - If agent asks about `$-2`: "Any negative bulk length other than `-1` is invalid and must raise, not silently return None."
- Corrections and hints:
  - If streaming tests fail because partial messages are consumed: "When `IncompleteError` is raised mid-parse, the buffer must not be modified — the position must not be committed."
  - If `test_invalid_type_byte_raises` fails because the error is swallowed: "The `_parse_one` function raises `ValueError` but `_parse()` catches `IncompleteError` only — let `ValueError` propagate out of `feed()` or re-raise it from `get_message()`."

**Completion Criteria:**

`pytest tests/ -x -q` passes all tests.
