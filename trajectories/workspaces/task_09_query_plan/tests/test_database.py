"""
Tests for the query system.
Run: pip install pytest && pytest tests/ -x -q
"""
import pytest
from database import Database


class TestBasicQueries:
    def test_insert_and_select_all_columns(self):
        db = Database()
        db.create_table("users", ["id", "name", "email"])
        db.insert("users", id=1, name="Alice", email="alice@example.com")
        rows = db.select("users", ["id", "name", "email"])
        assert rows == [{"id": 1, "name": "Alice", "email": "alice@example.com"}]

    def test_select_subset_of_columns(self):
        db = Database()
        db.create_table("users", ["id", "name", "email"])
        db.insert("users", id=1, name="Alice", email="alice@example.com")
        rows = db.select("users", ["name"])
        assert rows == [{"name": "Alice"}]

    def test_select_with_where(self):
        db = Database()
        db.create_table("users", ["id", "name"])
        db.insert("users", id=1, name="Alice")
        db.insert("users", id=2, name="Bob")
        rows = db.select("users", ["name"], where="id", eq=2)
        assert rows == [{"name": "Bob"}]

    def test_empty_table(self):
        db = Database()
        db.create_table("items", ["id", "value"])
        assert db.select("items", ["id", "value"]) == []

    def test_multiple_rows(self):
        db = Database()
        db.create_table("t", ["x", "y"])
        db.insert("t", x=1, y=10)
        db.insert("t", x=2, y=20)
        rows = db.select("t", ["x", "y"])
        assert len(rows) == 2
        assert {"x": 1, "y": 10} in rows
        assert {"x": 2, "y": 20} in rows


class TestSchemaEvolution:
    """
    Core correctness: queries must return correct data after ALTER TABLE.

    After adding a column, the schema's column index mapping changes.
    All components must agree on the new column layout:
      - schema.get_columns() must return the updated list
      - planner.plan() correctly re-plans (cache keyed by schema.version)
      - executor uses column indices from the fresh plan

    BUG: schema.get_columns() returns a stale cached list after ALTER TABLE.
    The planner correctly invalidates its plan cache (schema.version changed),
    builds a new plan by calling schema.column_index() — but column_index()
    calls get_columns() internally, which returns the OLD cached list.
    The new plan uses wrong column indices → queries return wrong values.

    The bug is in schema.py: alter_table() updates self._columns but does
    NOT update self._column_cache, so get_columns() keeps returning stale data.

    Fix: in alter_table(), after modifying self._columns[table], also update
    self._column_cache[table] (or simply delete the cache entry so it is
    rebuilt on next access).
    """

    def test_select_after_add_column_returns_correct_values(self):
        """
        After adding a column, selecting the original columns returns
        their original values — not values shifted by the new column layout.
        """
        db = Database()
        db.create_table("users", ["id", "name", "email"])
        db.insert("users", id=1, name="Alice", email="alice@example.com")

        # Add a new column before 'email' position is occupied
        db.alter_add_column("users", "age", default=0)
        # Now columns are: [id, name, email, age]

        rows = db.select("users", ["name"])
        assert rows == [{"name": "Alice"}], (
            f"Expected [{{'name': 'Alice'}}], got {rows}. "
            "After ALTER TABLE, schema.get_columns() is returning a stale "
            "cached column list. The planner invalidated its cache correctly "
            "(schema.version changed), but schema.column_index() — which the "
            "planner calls to build the new plan — uses get_columns() which "
            "still returns the pre-ALTER column list. "
            "Fix: invalidate schema._column_cache inside alter_table()."
        )

    def test_new_column_value_readable_after_alter(self):
        """Values inserted after ALTER TABLE include the new column."""
        db = Database()
        db.create_table("products", ["id", "name"])
        db.alter_add_column("products", "price", default=0)
        db.insert("products", id=1, name="Widget", price=999)
        rows = db.select("products", ["name", "price"])
        assert rows == [{"name": "Widget", "price": 999}]

    def test_existing_rows_have_default_for_new_column(self):
        """Rows inserted before ALTER TABLE get the default for the new column."""
        db = Database()
        db.create_table("items", ["id", "label"])
        db.insert("items", id=1, label="A")
        db.alter_add_column("items", "count", default=0)
        rows = db.select("items", ["label", "count"])
        assert rows == [{"label": "A", "count": 0}]

    def test_where_clause_correct_after_alter(self):
        """WHERE filtering uses correct column index after schema change."""
        db = Database()
        db.create_table("orders", ["id", "status", "total"])
        db.insert("orders", id=1, status="pending", total=100)
        db.insert("orders", id=2, status="shipped", total=200)

        db.alter_add_column("orders", "notes", default="")

        rows = db.select("orders", ["total"], where="status", eq="shipped")
        assert rows == [{"total": 200}], (
            f"Got {rows}. WHERE clause used wrong column index after ALTER TABLE."
        )

    def test_multiple_alters_consistent(self):
        """Schema remains consistent across multiple ALTER TABLE operations."""
        db = Database()
        db.create_table("t", ["a", "b"])
        db.insert("t", a=1, b=2)

        db.alter_add_column("t", "c", default=3)
        db.alter_add_column("t", "d", default=4)

        rows = db.select("t", ["a", "b", "c", "d"])
        assert rows == [{"a": 1, "b": 2, "c": 3, "d": 4}]

    def test_plan_cache_invalidated_after_alter(self):
        """The plan created before ALTER TABLE must not be reused after."""
        db = Database()
        db.create_table("events", ["ts", "type", "payload"])
        db.insert("events", ts=1, type="login", payload="x")

        # First query — plan cached
        before = db.select("events", ["type"])
        assert before == [{"type": "login"}]

        # Schema change
        db.alter_add_column("events", "user_id", default=None)
        db.insert("events", ts=2, type="logout", payload="y", user_id=42)

        # Second query — must use fresh plan with correct indices
        after = db.select("events", ["type"])
        types = {r["type"] for r in after}
        assert types == {"login", "logout"}, (
            f"Got {after}. Stale plan may be causing wrong column reads."
        )
