# Task: Fix SQL Query Builder

## User Persona

- **High-level goals:** Building an ORM-lite query builder for an internal analytics tool. Generates parameterized SQL from Python method chains.
- **Familiarity with tools:** Senior developer who writes SQL daily. Will spot invalid SQL immediately (HAVING before GROUP BY, OFFSET before LIMIT, etc.). Knows exactly what parameter order `sqlite3` / `psycopg2` expects.
- **Communication style:** Pastes the generated SQL and parameter list alongside the expected SQL. Very precise.
- **Patience style:** Will point out which specific clause is wrong. Will not tolerate invalid SQL.
- **Hint policy:** Will quote the SQL standard if the model generates structurally wrong SQL.

## Context

Implementation: `query_builder.py`. Tests: `tests/test_query_builder.py`.

```bash
cd /workspace && pip install pytest --quiet && pytest tests/ -x -q 2>&1 | tail -30
```

## Milestones

### Milestone 1: Fix Clause Ordering (HAVING, LIMIT/OFFSET)

**Initial Prompt:**

> "The query builder in `query_builder.py` generates SQL with clauses in the wrong order. `HAVING` sometimes appears before `GROUP BY`, and `OFFSET` appears before `LIMIT`. Both are invalid SQL. The tests `test_group_by_before_having`, `test_having_before_order_by`, and `test_limit_before_offset` show this. Fix the clause ordering in `build()`."

**Planned Interactions:**

- Clarification answers:
  - If agent asks what the correct SQL clause order is: "SELECT → FROM → JOIN → WHERE → GROUP BY → HAVING → ORDER BY → LIMIT → OFFSET"
- Corrections and hints:
  - If agent fixes HAVING but not LIMIT/OFFSET: "`test_limit_before_offset` still fails."
  - If agent emits OFFSET without LIMIT: "The test `test_offset_without_limit_raises` requires that `build()` raises `ValueError` if offset is set but limit is not — SQLite doesn't support OFFSET without LIMIT."

**Completion Criteria:**

`pytest tests/test_query_builder.py::TestGroupByHaving tests/test_query_builder.py::TestLimitOffset -x -q` passes.

---

### Milestone 2: Fix Parameter Ordering with JOINs

**Initial Prompt:**

> "Parameter ordering is wrong when there's a JOIN + WHERE + HAVING. The params list should be `[where_params..., having_params...]` — WHERE params first, HAVING params after. But I'm getting them mixed up or in the wrong order. See `test_join_with_where_params_in_correct_order`."

**Planned Interactions:**

- Clarification answers:
  - If agent asks about the expected param order: "WHERE params come before HAVING params in the `params` list, because that's the order they appear in the SQL."
- Corrections and hints:
  - If agent collects HAVING params before WHERE: "The params list still has them in the wrong order — collect WHERE first, then HAVING."

**Completion Criteria:**

`pytest tests/test_query_builder.py::TestJoin -x -q` passes all 4 tests.

---

### Milestone 3: Fix OFFSET Without LIMIT Validation and Full Suite

**Initial Prompt:**

> "Run the full test suite. Make sure `test_offset_without_limit_raises` passes — currently `build()` emits `OFFSET 20` with no LIMIT, which is invalid. Raise a `ValueError` in that case."

**Planned Interactions:**

- Corrections and hints:
  - If agent raises an error in `offset()` instead of `build()`: "The error should be raised in `build()`, not in `offset()` — the user might set offset then add a limit later in the chain."

**Completion Criteria:**

`pytest tests/ -x -q` passes all tests.
