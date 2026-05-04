# Task: Fix Package Dependency Resolver

## User Persona

- **High-level goals:** Building a pip-like dependency resolver for a private package registry. Must correctly handle version ranges and catch transitive conflicts.
- **Familiarity with tools:** Has worked with pip's resolver and understands SemVer. Knows that `>=2.0.0` must accept exactly 2.0.0 — inclusive boundary.
- **Communication style:** Writes minimal reproducing cases: "resolver.resolve(['pkg>=2.0.0']) with only pkg@2.0.0 available should succeed, but it raises ConflictError."
- **Patience style:** Will escalate to a simpler reproducer if the fix doesn't work.
- **Hint policy:** Will not suggest which comparison operator to change. Will only describe the wrong output.

## Context

Implementation: `resolver.py`. Tests: `tests/test_resolver.py`.

```bash
cd /workspace && pip install pytest --quiet && pytest tests/ -x -q 2>&1 | tail -30
```

## Milestones

### Milestone 1: Fix Inclusive Boundary in Constraint.satisfied_by()

**Initial Prompt:**

> "Resolving `pkg>=2.0.0` when only `pkg@2.0.0` is available raises ConflictError. It should succeed — `>=` means 'greater than or equal to', so 2.0.0 satisfies `>=2.0.0`. Same for `<=`. Fix `resolver.py`."

**Planned Interactions:**

- Clarification answers:
  - If agent asks which class: "The `Constraint.satisfied_by()` method in `resolver.py`."
  - If agent asks about `>` and `<`: "Those should remain strict (exclusive). Only `>=` and `<=` need to include the boundary."
- Corrections and hints:
  - If agent fixes `>=` but not `<=`: "`test_exact_boundary_lte` still fails."
  - If agent accidentally makes `>` inclusive: "`test_strict_greater` would now fail."

**Completion Criteria:**

`pytest tests/test_resolver.py::TestConstraint tests/test_resolver.py::TestResolverBasic -x -q` passes.

---

### Milestone 2: Fix Transitive Dependency Resolution

**Initial Prompt:**

> "The resolver doesn't catch transitive conflicts. If `app` requires `libA>=2.0`, and `libA@2.0` requires `libB>=3.0`, but only `libB@2.9` is available, the resolver should raise ConflictError — but it doesn't. It silently returns the wrong result. Fix it."

**Planned Interactions:**

- Clarification answers:
  - If agent asks what's missing: "When you select a package, you must also resolve ITS dependencies and check for conflicts, recursively."
  - If agent asks about cycle prevention: "Keep a visited set to avoid infinite loops on circular dependencies."
- Corrections and hints:
  - If agent resolves transitively but conflicts aren't caught: "The constraint from `libA`'s deps must be combined with any other constraints for that package before selecting a version."

**Completion Criteria:**

`pytest tests/ -x -q` passes all tests including `TestResolverDeps`.
