"""
Query executor: runs QueryPlans against in-memory table data.
"""
from __future__ import annotations
from planner import QueryPlan


class Executor:
    def __init__(self):
        # table_name → list of rows, each row is a list of values
        self._tables: dict[str, list[list]] = {}

    def insert(self, table: str, row: list) -> None:
        self._tables.setdefault(table, []).append(list(row))

    def execute(self, plan: QueryPlan) -> list[dict]:
        """
        Run *plan* against stored data and return matching rows as dicts.
        Column names are taken from plan.project_indices applied to each row.
        """
        rows = self._tables.get(plan.table, [])
        results = []
        for row in rows:
            # Apply WHERE filter
            if plan.filter_col_idx is not None:
                if plan.filter_col_idx >= len(row):
                    continue
                if row[plan.filter_col_idx] != plan.filter_value:
                    continue
            # Project requested columns
            projected = {
                f"col{idx}": row[idx]
                for idx in plan.project_indices
                if idx < len(row)
            }
            results.append(projected)
        return results

    def add_column(self, table: str, default=None) -> None:
        """Extend existing rows with a new column (default value)."""
        for row in self._tables.get(table, []):
            row.append(default)
