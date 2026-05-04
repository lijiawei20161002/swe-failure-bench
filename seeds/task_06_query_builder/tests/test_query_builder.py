"""Tests for QueryBuilder. Run: pytest tests/ -x"""
import re
import pytest
from query_builder import Query


def normalize(sql: str) -> str:
    """Collapse whitespace/newlines for comparison."""
    return re.sub(r"\s+", " ", sql).strip()


# ── basic SELECT ──────────────────────────────────────────────────────────────

class TestSelect:
    def test_select_star(self):
        sql, params = Query("users").build()
        assert "SELECT *" in normalize(sql)
        assert "FROM users" in normalize(sql)
        assert params == []

    def test_select_columns(self):
        sql, params = Query("users").select("id", "name").build()
        assert "SELECT id, name" in normalize(sql)

    def test_where_single(self):
        sql, params = Query("users").where("active = ?", True).build()
        assert "WHERE active = ?" in normalize(sql)
        assert params == [True]

    def test_where_multiple(self):
        sql, params = (
            Query("users")
            .where("active = ?", True)
            .where("age > ?", 18)
            .build()
        )
        n = normalize(sql)
        assert "WHERE" in n
        assert "active = ?" in n
        assert "age > ?" in n
        assert "AND" in n
        assert params == [True, 18]


# ── JOINs ────────────────────────────────────────────────────────────────────

class TestJoin:
    def test_inner_join(self):
        sql, params = (
            Query("users")
            .join("orders", on="users.id = orders.user_id")
            .build()
        )
        n = normalize(sql)
        assert "INNER JOIN orders ON users.id = orders.user_id" in n

    def test_left_join(self):
        sql, _ = (
            Query("users")
            .join("orders", on="users.id = orders.user_id", join_type="LEFT")
            .build()
        )
        assert "LEFT JOIN" in normalize(sql)

    def test_join_with_where_params_in_correct_order(self):
        """WHERE params must appear before HAVING params in the params list."""
        sql, params = (
            Query("users")
            .join("orders", on="users.id = orders.user_id")
            .where("users.active = ?", True)
            .where("orders.total > ?", 100)
            .group_by("users.id")
            .having("COUNT(orders.id) > ?", 2)
            .build()
        )
        # Expected order: [True, 100, 2]
        assert params == [True, 100, 2], f"wrong param order: {params}"

    def test_join_clause_before_where(self):
        """JOIN must appear before WHERE in the generated SQL."""
        sql, _ = (
            Query("users")
            .join("orders", on="users.id = orders.user_id")
            .where("users.id > ?", 0)
            .build()
        )
        n = normalize(sql)
        assert n.index("JOIN") < n.index("WHERE"), (
            f"JOIN should appear before WHERE, got: {n}"
        )


# ── GROUP BY / HAVING ─────────────────────────────────────────────────────────

class TestGroupByHaving:
    def test_group_by(self):
        sql, _ = Query("orders").group_by("user_id").build()
        assert "GROUP BY user_id" in normalize(sql)

    def test_having(self):
        sql, params = (
            Query("orders")
            .group_by("user_id")
            .having("SUM(total) > ?", 500)
            .build()
        )
        assert "HAVING SUM(total) > ?" in normalize(sql)
        assert params == [500]

    def test_group_by_before_having(self):
        """GROUP BY must appear before HAVING in the generated SQL."""
        sql, _ = (
            Query("orders")
            .group_by("user_id")
            .having("COUNT(*) > ?", 1)
            .build()
        )
        n = normalize(sql)
        assert n.index("GROUP BY") < n.index("HAVING"), (
            f"GROUP BY should come before HAVING: {n}"
        )

    def test_having_before_order_by(self):
        sql, _ = (
            Query("orders")
            .group_by("user_id")
            .having("COUNT(*) > ?", 1)
            .order_by("user_id")
            .build()
        )
        n = normalize(sql)
        assert n.index("HAVING") < n.index("ORDER BY"), (
            f"HAVING should come before ORDER BY: {n}"
        )


# ── LIMIT / OFFSET ────────────────────────────────────────────────────────────

class TestLimitOffset:
    def test_limit_only(self):
        sql, _ = Query("users").limit(10).build()
        assert "LIMIT 10" in normalize(sql)
        assert "OFFSET" not in normalize(sql)

    def test_limit_before_offset(self):
        """LIMIT must appear before OFFSET in the generated SQL."""
        sql, _ = Query("users").limit(10).offset(20).build()
        n = normalize(sql)
        assert "LIMIT 10" in n
        assert "OFFSET 20" in n
        assert n.index("LIMIT") < n.index("OFFSET"), (
            f"LIMIT should come before OFFSET: {n}"
        )

    def test_offset_without_limit_raises(self):
        """OFFSET without LIMIT is not valid SQL; should raise ValueError."""
        with pytest.raises(ValueError):
            Query("users").offset(20).build()


# ── subquery ──────────────────────────────────────────────────────────────────

class TestSubquery:
    def test_subquery_fragment(self):
        inner = Query("orders").select("user_id", "SUM(total) AS total").group_by("user_id")
        frag, params = inner.subquery("order_totals").build_fragment()
        assert frag.startswith("(")
        assert "order_totals" in frag

    def test_subquery_in_from(self):
        """A Subquery can be used as the table in an outer Query."""
        inner = Query("orders").select("user_id", "SUM(total) AS total").group_by("user_id")
        sub = inner.subquery("order_totals")
        frag, inner_params = sub.build_fragment()
        outer_sql, outer_params = (
            Query(frag)    # use the fragment as the table expression
            .select("user_id", "total")
            .where("total > ?", 1000)
            .build()
        )
        # Verify param ordering: inner query params come before outer WHERE params
        all_params = inner_params + outer_params
        assert all_params == [1000], f"expected [1000], got {all_params}"
        assert "order_totals" in normalize(outer_sql)
