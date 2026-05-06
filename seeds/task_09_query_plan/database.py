"""
Database: high-level API combining schema, planner, and executor.
"""
from __future__ import annotations
from schema import Schema
from planner import Planner
from executor import Executor


class Database:
    def __init__(self):
        self.schema = Schema()
        self._planner = Planner(self.schema)
        self._executor = Executor()

    def create_table(self, table: str, columns: list[str]) -> None:
        self.schema.create_table(table, columns)

    def insert(self, table: str, **values) -> None:
        cols = self.schema.get_columns(table)
        row = [values.get(c) for c in cols]
        self._executor.insert(table, row)

    def alter_add_column(self, table: str, column: str, default=None) -> None:
        """Add a column to an existing table."""
        self.schema.alter_table(table, add_columns=[column])
        self._executor.add_column(table, default=default)

    def select(self, table: str, columns: list[str],
               where: str | None = None, eq=None) -> list[dict]:
        """
        Execute a SELECT and return rows as dicts mapping column_name → value.
        """
        plan = self._planner.plan(table, columns, where_col=where, where_val=eq)
        raw = self._executor.execute(plan)

        # Map col0/col1/… keys back to column names using current schema indices
        col_names = {
            self.schema.column_index(table, c): c
            for c in columns
        }
        return [
            {col_names[int(k[3:])]: v for k, v in row.items()}
            for row in raw
        ]
