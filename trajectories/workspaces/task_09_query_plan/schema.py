"""
Table schema registry.

Tracks column definitions and schema versions.  Every structural change
(add/drop/rename column) increments the schema version so that downstream
consumers (e.g. query planners) can detect stale cached data.

Usage:
    schema = Schema()
    schema.create_table("users", ["id", "name", "email"])
    schema.get_columns("users")      # → ["id", "name", "email"]
    schema.alter_table("users", add_columns=["age"])
    schema.get_columns("users")      # → ["id", "name", "email", "age"]
"""
from __future__ import annotations


class SchemaError(Exception):
    pass


class Schema:
    def __init__(self):
        # Ground-truth column definitions: table_name → list of column names
        self._columns: dict[str, list[str]] = {}

        # Monotonically increasing version; increments on every structural change.
        self.version: int = 0

    def create_table(self, table: str, columns: list[str]) -> None:
        if table in self._columns:
            raise SchemaError(f"Table {table!r} already exists")
        self._columns[table] = list(columns)
        self.version += 1

    def alter_table(
        self,
        table: str,
        add_columns: list[str] | None = None,
        drop_columns: list[str] | None = None,
    ) -> None:
        if table not in self._columns:
            raise SchemaError(f"Table {table!r} does not exist")

        if add_columns:
            for col in add_columns:
                if col in self._columns[table]:
                    raise SchemaError(f"Column {col!r} already exists in {table!r}")
                self._columns[table].append(col)

        if drop_columns:
            for col in drop_columns:
                if col not in self._columns[table]:
                    raise SchemaError(f"Column {col!r} not in {table!r}")
                self._columns[table].remove(col)

        self.version += 1

    def get_columns(self, table: str) -> list[str]:
        """Return the column names for *table* in definition order."""
        if table not in self._columns:
            raise SchemaError(f"Table {table!r} does not exist")
        return list(self._columns[table])

    def has_table(self, table: str) -> bool:
        return table in self._columns

    def column_index(self, table: str, column: str) -> int:
        """Return the 0-based index of *column* in *table*'s column list."""
        cols = self.get_columns(table)
        try:
            return cols.index(column)
        except ValueError:
            raise SchemaError(f"Column {column!r} not found in {table!r}")
