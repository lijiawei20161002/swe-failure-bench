"""
SQL query builder — builds parameterized SELECT statements.

Modelled after Peewee / SQLAlchemy Core expression patterns.

Example usage:
    q = (Query("users")
         .select("id", "name", "email")
         .join("orders", on="users.id = orders.user_id")
         .where("users.active = ?", True)
         .where("orders.total > ?", 100)
         .group_by("users.id")
         .having("COUNT(orders.id) > ?", 2)
         .order_by("users.name")
         .limit(10))

    sql, params = q.build()
    # sql  → "SELECT id, name, email FROM users ..."
    # params → [True, 100, 2]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Query:
    table: str
    _select: list[str] = field(default_factory=list)
    _joins: list[tuple[str, str, str]] = field(default_factory=list)
    _wheres: list[tuple[str, list]] = field(default_factory=list)
    _group_by: list[str] = field(default_factory=list)
    _havings: list[tuple[str, list]] = field(default_factory=list)
    _order_by: list[str] = field(default_factory=list)
    _limit: int | None = None
    _offset: int | None = None

    def select(self, *cols: str) -> "Query":
        self._select.extend(cols)
        return self

    def join(self, table: str, *, on: str, join_type: str = "INNER") -> "Query":
        self._joins.append((table, on, join_type))
        return self

    def where(self, clause: str, *params) -> "Query":
        self._wheres.append((clause, list(params)))
        return self

    def group_by(self, *cols: str) -> "Query":
        self._group_by.extend(cols)
        return self

    def having(self, clause: str, *params) -> "Query":
        self._havings.append((clause, list(params)))
        return self

    def order_by(self, *cols: str) -> "Query":
        self._order_by.extend(cols)
        return self

    def limit(self, n: int) -> "Query":
        self._limit = n
        return self

    def offset(self, n: int) -> "Query":
        self._offset = n
        return self

    def build(self) -> tuple[str, list[Any]]:
        """Return (sql_string, params_list)."""
        params: list[Any] = []
        parts: list[str] = []

        # SELECT
        cols = ", ".join(self._select) if self._select else "*"
        parts.append(f"SELECT {cols}")

        # FROM
        parts.append(f"FROM {self.table}")

        # JOINs
        for jtable, jcond, jtype in self._joins:
            parts.append(f"{jtype} JOIN {jtable} ON {jcond}")

        # WHERE
        if self._wheres:
            clauses = []
            for clause, p in self._wheres:
                clauses.append(clause)
                params.extend(p)
            parts.append("WHERE " + " AND ".join(clauses))

        # GROUP BY
        if self._group_by:
            parts.append("GROUP BY " + ", ".join(self._group_by))

        # HAVING
        if self._havings:
            having_clauses = []
            for clause, p in self._havings:
                having_clauses.append(clause)
                params.extend(p)
            parts.append("HAVING " + " AND ".join(having_clauses))

        # ORDER BY
        if self._order_by:
            parts.append("ORDER BY " + ", ".join(self._order_by))

        # LIMIT / OFFSET
        if self._limit is not None:
            parts.append(f"LIMIT {self._limit}")
        if self._offset is not None:
            if self._limit is None:
                raise ValueError("OFFSET without LIMIT is not valid SQL")
            parts.append(f"OFFSET {self._offset}")

        sql = "\n".join(parts)
        return sql, params

    def subquery(self, alias: str) -> "Subquery":
        """Wrap this query as a subquery with an alias."""
        return Subquery(self, alias)


@dataclass
class Subquery:
    query: Query
    alias: str

    def build_fragment(self) -> tuple[str, list]:
        sql, params = self.query.build()
        return f"({sql}) AS {self.alias}", params
