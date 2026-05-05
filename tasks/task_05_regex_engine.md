# Task: Fix NFA-Based Regex Engine

## User Persona

- **High-level goals:** Building a sandboxed regex engine using Thompson NFA construction. Must match Python's `re` module semantics for supported features.
- **Familiarity with tools:** Read Russ Cox's "Regular Expression Matching Can Be Simple And Fast". Knows NFA simulation. Will notice immediately if basic literals don't work.
- **Communication style:** Runs `engine.match("abc", "abc")` and sees an exception — "There's a TypeError before even getting to the real bugs."
- **Patience style:** Will escalate through bugs systematically: first crash, then wrong alternation, then wrong character classes.
- **Hint policy:** After fix of TypeError: "The ε-closure for a split state must follow BOTH out1 and out2." Will not explain further.

## Context

Implementation: `regex_engine.py`. Tests: `tests/test_regex.py`.

```bash
cd /workspace && pip install pytest --quiet && pytest tests/ -x -q 2>&1 | tail -30
```

## Milestones

### Milestone 1: Fix the TypeError (unhashable State)

**Initial Prompt:**

> "Everything crashes with `TypeError: unhashable type: 'State'` before even running a pattern. The `State` dataclass can't be used in sets. Fix it."

**Planned Interactions:**

- Clarification answers:
  - If agent asks: "The State objects need identity-based hashing (use `id()`), not value-based. Add `unsafe_hash=True` or `eq=False` to the dataclass."
- Corrections and hints:
  - If agent uses `__hash__ = object.__hash__` but breaks equality: "NFA states only need identity equality, not value equality."

**Completion Criteria:**

`pytest tests/test_regex.py::TestLiterals tests/test_regex.py::TestDot tests/test_regex.py::TestQuantifiers -x -q` passes.

---

### Milestone 2: Fix ε-Closure for Alternation

**Initial Prompt:**

> "Literals and quantifiers work but alternation is broken — `engine.match('a|b', 'b')` returns None. The split state for `|` creates two branches, but only one branch is ever reached. Look at `_e_closure` in `regex_engine.py`."

**Planned Interactions:**

- Clarification answers:
  - If agent asks what ε-closure should do: "For a split state (transition=EPSILON), both out1 AND out2 are ε-transitions and both must be followed."
- Corrections and hints:
  - If agent adds out2 traversal but `(a|b)*` still fails: "Verify the ε-closure is computed iteratively until no new states are added."

**Completion Criteria:**

`pytest tests/test_regex.py::TestAlternation -x -q` passes all tests.

---

### Milestone 3: Fix Character Class Range Parsing

**Initial Prompt:**

> "Alternation works. Last bug: `[a-z]` should match any lowercase letter but only matches 'a', '-', and 'z'. The character class parser needs to expand ranges."

**Planned Interactions:**

- Clarification answers:
  - If agent asks about the syntax: "`[a-z]` means all characters with code points between 'a' and 'z'. Check for '-' between two characters and expand with `range(ord(lo), ord(hi)+1)`."
- Corrections and hints:
  - If agent fixes ranges but negated ranges break: "`[^0-9]` should also work with ranges."

**Completion Criteria:**

`pytest tests/ -x -q` passes all tests including `test_matches_agree_with_stdlib`.
