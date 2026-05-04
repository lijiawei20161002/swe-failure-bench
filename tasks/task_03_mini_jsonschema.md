# Task: Fix JSON Schema Validator

## User Persona

- **High-level goals:** Building an API gateway that validates request bodies against JSON Schema. Started with a minimal validator (`validator.py`) for draft-07 features but hit bugs.
- **Familiarity with tools:** Experienced Python developer who reads the JSON Schema spec when stuck. Not familiar with the specific semantic edge cases of `oneOf` vs `anyOf`. Has used `jsonschema` library before.
- **Communication style:** Shares failing tests immediately. Quotes the spec if they know the rule.
- **Patience style:** 2 attempts per bug before moving on. Won't ask for the same fix three times.
- **Hint policy:** Will quote the relevant part of the JSON Schema spec if the model is clearly going in the wrong direction.

## Context

Implementation: `validator.py`. Tests: `tests/test_validator.py`.

```bash
cd /workspace && pip install pytest --quiet && pytest tests/ -x -q 2>&1 | tail -30
```

## Milestones

### Milestone 1: Fix `additionalProperties: false`

**Initial Prompt:**

> "My JSON Schema validator isn't enforcing `additionalProperties: false`. If I have a schema with only `{'properties': {'x': ...}, 'additionalProperties': false}` and I pass `{'x': 1, 'y': 2}`, it should raise `ValidationError` because 'y' is not declared. Look at `validator.py` and fix it. The tests are in `TestObject`."

**Planned Interactions:**

- Clarification answers:
  - If agent asks about `additionalProperties` as a schema (not just `false`): "Yes, `additionalProperties` can also be a schema — extra keys must validate against it. Both cases need to work."
- Corrections and hints:
  - If agent only handles the `false` case: "Good, but `test_additional_properties_schema` still fails — `additionalProperties` can also be a schema that additional keys must satisfy."
  - If agent checks unknown keys against `additionalProperties` schema but forgets to handle `false` as a special case: "The `false` case is also broken — it should reject any extra key, not validate against a schema."

**Completion Criteria:**

`pytest tests/test_validator.py::TestObject -x -q` passes all 5 tests.

---

### Milestone 2: Fix `$ref` Resolution

**Initial Prompt:**

> "Now fix `$ref`. The validator supports `#/$defs/<name>` refs but they don't work when `$ref` appears inside a property value. Also a `$ref` to a nonexistent name should raise `ValidationError`, not silently pass. See `TestRef`."

**Planned Interactions:**

- Clarification answers:
  - If agent asks whether to support external `$ref` URIs: "No, only local JSON pointer refs (`#/$defs/...` and `#/definitions/...`)."
  - If agent asks about nested refs: "`$defs` can reference each other — `test_nested_ref` checks that."
- Corrections and hints:
  - If agent handles top-level `$ref` but not within properties: "The `test_ref_in_property` test still fails — a `{'$ref': '#/$defs/Name'}` inside `properties` needs to be resolved too. The `_defs` context must be threaded through."
  - If agent loses `_defs` during recursive property validation: "Nested refs break because `_defs` isn't passed when you recurse into property sub-schemas."

**Completion Criteria:**

`pytest tests/test_validator.py::TestRef -x -q` passes all 4 tests.

---

### Milestone 3: Fix `oneOf` Semantics

**Initial Prompt:**

> "Last one: `oneOf` must match exactly one sub-schema. Right now it behaves like `anyOf` — it stops at the first match. If the instance matches two or more sub-schemas, it should raise `ValidationError`. Fix it. See `TestOneOf`."

**Planned Interactions:**

- Clarification answers:
  - If agent asks what the JSON Schema spec says: "`oneOf` — the given data must be valid against exactly one of the given subschemas."
- Corrections and hints:
  - If agent counts matches but breaks early: "The `test_two_matches_raises` case still passes incorrectly. You need to run all sub-schema checks, not stop at the first match."

**Completion Criteria:**

`pytest tests/ -x -q` passes all tests across all test classes.
