"""
Query planner with schema-version-aware plan caching.

A query plan records which column indices to project from each row.
Plans are expensive to compute (in production: parsing, optimization,
cost estimation).  The planner caches plans keyed by
(query_string, schema_version) so they are automatically invalidated
whenever the schema changes.
"""
from __future__ import annotations
from dataclasses import dataclass
from schema import Schema


@dataclass
class QueryPlan:
    table: str
    project_indices: list[int]    # column indices to include in output
    filter_col_idx: int | None    # column index for WHERE clause
    filter_value: object          # value to match


class Planner:
    def __init__(self, schema: Schema):
        self._schema = schema
        # Cache key: (query_string, schema_version) — correctly invalidated
        # on schema changes because schema.version increments on ALTER TABLE.
        self._cache: dict[tuple, QueryPlan] = {}

    def plan(self, table: str, select_cols: list[str],
             where_col: str | None = None, where_val: object = None) -> QueryPlan:
        query_key = (table, tuple(select_cols), where_col, where_val,
                     self._schema.version)   # version in key → cache invalidated on ALTER

        if query_key in self._cache:
            return self._cache[query_key]

        # Build a fresh plan using current schema
        project_indices = [self._schema.column_index(table, c) for c in select_cols]
        filter_idx = (self._schema.column_index(table, where_col)
                      if where_col else None)

        plan = QueryPlan(
            table=table,
            project_indices=project_indices,
            filter_col_idx=filter_idx,
            filter_value=where_val,
        )
        self._cache[query_key] = plan
        return plan
