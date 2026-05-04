# Task: Fix Event Emitter with Wildcards and Weak References

## User Persona

- **High-level goals:** Building a pub/sub event bus for a Python desktop application. Widgets subscribe to events; the bus must not keep widgets alive past their lifetime. Also needs glob-style wildcard routing.
- **Familiarity with tools:** Experienced Python developer. Understands weakrefs conceptually. Has used Node.js EventEmitter before and expects similar semantics.
- **Communication style:** Will share minimal reproduction cases. Tracks which handlers were called and which weren't. Notices silently dropped events.
- **Patience style:** Tolerates one debugging round per bug. Will be explicit about the expected vs actual handler call counts.
- **Hint policy:** Will mention "I think it's the fnmatch not handling dots" if wildcard matching is clearly wrong. Won't go further.

## Context

Implementation: `event_emitter.py`. Tests: `tests/test_event_emitter.py`.

```bash
cd /workspace && pip install pytest --quiet && pytest tests/ -x -q 2>&1 | tail -30
```

## Milestones

### Milestone 1: Fix Wildcard Pattern Matching

**Initial Prompt:**

> "The wildcard matching in `event_emitter.py` is broken. When I subscribe to `'user.*'`, it should match `'user.login'` but NOT `'user.login.extra'` — the single `*` should match exactly one dot-separated segment. And `'order.**'` should match any number of trailing segments. Right now `fnmatch` is used which doesn't respect dots. Fix the `_matches()` function. Tests are in `TestWildcards`."

**Planned Interactions:**

- Clarification answers:
  - If agent asks about the `**` edge case: "`'order.**'` should also match `'order'` itself — zero trailing segments."
  - If agent asks whether `*` matches an empty segment: "No — `'user.*'` does NOT match `'user'`, it needs at least one character after the dot."
- Corrections and hints:
  - If agent splits on dots and compares but doesn't handle `**`: "`test_double_star_matches_multiple_segments` still fails — `**` should match zero or more dot-separated segments."
  - If agent handles `*` but `**` requires at least one segment: "`test_double_star_matches_zero_extra_segments` fails — `'order.**'` should match `'order'` itself."

**Completion Criteria:**

`pytest tests/test_event_emitter.py::TestWildcards -x -q` passes all 6 tests.

---

### Milestone 2: Fix Error Isolation Between Handlers

**Initial Prompt:**

> "Even when wildcard matching works, an exception in one handler kills the whole `emit()` call and subsequent handlers never run. Fix `emit()` so that each handler's exception is caught, collected in `self._errors`, and emit continues to the next handler. See `TestErrorIsolation`."

**Planned Interactions:**

- Corrections and hints:
  - If agent wraps in try/except but still re-raises: "The re-raise is the problem — catch it, append to `self._errors`, then continue the loop."
  - If agent uses `continue` after appending but count is wrong: "You append the error but also increment `called` — a handler that raised shouldn't count as 'called' successfully? Actually check what the tests assert."

**Completion Criteria:**

`pytest tests/test_event_emitter.py::TestErrorIsolation -x -q` passes.

---

### Milestone 3: Fix Weak Reference Handling for Bound Methods

**Initial Prompt:**

> "Last issue: when `weak=True` (the default), the handler should be stored as a weak reference so it doesn't prevent garbage collection. `test_dead_weakref_not_called` creates an object, subscribes its bound method, deletes the object, and expects the handler NOT to be called. But weakrefs to bound methods don't work naively because bound methods are created fresh each time. Fix the `_Handler` class to use `weakref.WeakMethod` for bound methods."

**Planned Interactions:**

- Clarification answers:
  - If agent asks what `weakref.WeakMethod` is: "It's in the standard library — `import weakref; weakref.WeakMethod(bound_method)`. It holds a weak ref to both the function and the instance."
  - If agent asks whether all callables can be weakly referenced: "No — builtins can't. Fall back to strong references for those (the existing code already has that fallback)."
- Corrections and hints:
  - If agent uses `weakref.ref` on a bound method: "`test_dead_weakref_not_called` will still fail — `weakref.ref(obj.method)` creates a weakref to a throwaway bound method object, which dies immediately."
  - If agent uses `WeakMethod` but `test_live_weakref_called` fails: "The live ref test means the method must still be callable before the object is deleted."

**Completion Criteria:**

`pytest tests/ -x -q` passes all tests.
