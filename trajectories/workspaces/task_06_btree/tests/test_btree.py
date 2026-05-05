"""Tests for B-tree. Run: pytest tests/ -x"""
import random
import pytest
from btree import BTree, BTreeCursor


# ── basic search / insert ─────────────────────────────────────────────────────

class TestBasic:
    def test_insert_and_search(self):
        tree = BTree(t=2)
        for k in [10, 20, 5, 6, 12, 30, 7, 17]:
            tree.insert(k)
        for k in [10, 20, 5, 6, 12, 30, 7, 17]:
            assert tree.search(k), f"key {k} not found after insert"

    def test_search_missing(self):
        tree = BTree(t=2)
        tree.insert(1)
        assert not tree.search(99)

    def test_sorted_order(self):
        keys = [5, 3, 8, 1, 9, 2, 7, 4, 6]
        tree = BTree(t=2)
        for k in keys:
            tree.insert(k)
        assert list(tree) == sorted(keys)

    def test_large_t(self):
        tree = BTree(t=4)
        keys = list(range(50))
        random.shuffle(keys)
        for k in keys:
            tree.insert(k)
        assert list(tree) == list(range(50))


# ── split invariant (BUG A) ───────────────────────────────────────────────────

class TestSplitInvariant:
    def test_split_promotes_correct_median(self):
        """
        When a full node with 2t-1 keys is split, the median key (index t-1)
        is promoted to the parent. Keys at indices 0..t-2 stay in the left
        child; keys at indices t..2t-2 go to the right child.

        With t=2 and a node [1,2,3] (2*2-1=3 keys):
          median = keys[1] = 2  (0-indexed, t-1=1)
          left  = [1]           (keys[:t-1] = keys[:1])
          right = [3]           (keys[t:]   = keys[2:])
        """
        tree = BTree(t=2)
        # Insert enough to force a root split: 4 keys fill root (2t-1=3), 5th forces split
        for k in [10, 20, 30, 40, 50]:
            tree.insert(k)
        assert list(tree) == [10, 20, 30, 40, 50], (
            f"After 5 inserts into t=2 tree, expected sorted order. Got {list(tree)}"
        )

    def test_split_does_not_duplicate_keys(self):
        """After any sequence of inserts, no key should appear twice."""
        tree = BTree(t=2)
        keys = [3, 1, 4, 1, 5, 9, 2, 6, 5, 3, 5]
        for k in keys:
            try:
                tree.insert(k)
            except Exception:
                pass
        all_keys = list(tree)
        assert len(all_keys) == len(set(all_keys)), f"Duplicate keys found: {all_keys}"

    def test_split_preserves_all_keys(self):
        """After splitting, no key should be lost."""
        tree = BTree(t=3)
        keys = list(range(1, 30))
        for k in keys:
            tree.insert(k)
        found = [tree.search(k) for k in keys]
        missing = [k for k, f in zip(keys, found) if not f]
        assert not missing, f"Keys lost after splits: {missing}"

    def test_many_inserts_sorted(self):
        """Property: list(tree) == sorted(inserted_keys) for any order."""
        for seed in range(5):
            random.seed(seed)
            keys = random.sample(range(1000), 100)
            tree = BTree(t=2)
            for k in keys:
                tree.insert(k)
            assert list(tree) == sorted(keys), (
                f"Sorted traversal wrong for seed={seed}"
            )


# ── delete ────────────────────────────────────────────────────────────────────

class TestDelete:
    def test_delete_leaf_key(self):
        tree = BTree(t=2)
        for k in [1, 2, 3, 4, 5]:
            tree.insert(k)
        tree.delete(3)
        assert not tree.search(3)
        assert list(tree) == [1, 2, 4, 5]

    def test_delete_internal_key(self):
        tree = BTree(t=2)
        for k in range(1, 15):
            tree.insert(k)
        tree.delete(7)
        assert not tree.search(7)
        assert list(tree) == [k for k in range(1, 15) if k != 7]

    def test_delete_nonexistent_raises(self):
        tree = BTree(t=2)
        tree.insert(5)
        with pytest.raises(KeyError):
            tree.delete(99)

    def test_delete_all_keys(self):
        tree = BTree(t=2)
        keys = list(range(20))
        for k in keys:
            tree.insert(k)
        for k in keys:
            tree.delete(k)
        assert list(tree) == []

    def test_insert_delete_property(self):
        """Invariant: after any inserts+deletes, list(tree) == sorted remaining keys."""
        random.seed(42)
        inserted = set()
        tree = BTree(t=2)
        for _ in range(50):
            k = random.randint(0, 30)
            if k not in inserted:
                tree.insert(k)
                inserted.add(k)
        to_delete = random.sample(list(inserted), 20)
        for k in to_delete:
            tree.delete(k)
            inserted.remove(k)
        assert list(tree) == sorted(inserted)


# ── cursor (BUG B) ────────────────────────────────────────────────────────────

class TestCursor:
    def test_cursor_basic(self):
        tree = BTree(t=2)
        for k in [3, 1, 2]:
            tree.insert(k)
        cursor = tree.cursor()
        results = []
        while cursor.has_next():
            results.append(cursor.next())
        assert results == [1, 2, 3]

    def test_cursor_reflects_deletions_after_creation(self):
        """
        A key deleted AFTER cursor creation but BEFORE cursor.next() reaches
        it must be skipped — the cursor must not return deleted keys.

        Timeline:
          tree = {1, 2, 3, 4, 5}
          cursor = tree.cursor()    ← created here
          cursor.next()             → returns 1
          tree.delete(3)            ← delete key 3
          cursor.next()             → returns 2
          cursor.next()             → must return 4, NOT 3 (which is deleted)
          cursor.next()             → returns 5
        """
        tree = BTree(t=2)
        for k in [1, 2, 3, 4, 5]:
            tree.insert(k)
        cursor = tree.cursor()
        assert cursor.next() == 1
        assert cursor.next() == 2
        tree.delete(3)
        nxt = cursor.next()
        assert nxt == 4, (
            f"Cursor returned {nxt} but key 3 was deleted after cursor creation. "
            "Expected 4. BUG B: cursor snapshots keys at creation, so it still "
            "returns deleted keys."
        )
        assert cursor.next() == 5

    def test_cursor_includes_future_insertions_in_remaining_range(self):
        """
        A key inserted AFTER cursor creation, whose value > last returned key,
        must appear in subsequent cursor.next() calls.

        Timeline:
          tree = {1, 3, 5}
          cursor = tree.cursor()
          cursor.next()             → returns 1
          tree.insert(4)            ← insert 4 (> 1, not yet passed)
          cursor.next()             → must return 3
          cursor.next()             → must return 4 (newly inserted, in range)
          cursor.next()             → returns 5
        """
        tree = BTree(t=2)
        for k in [1, 3, 5]:
            tree.insert(k)
        cursor = tree.cursor()
        assert cursor.next() == 1
        tree.insert(4)
        assert cursor.next() == 3
        nxt = cursor.next()
        assert nxt == 4, (
            f"Cursor returned {nxt} but key 4 was inserted after creation in the "
            "not-yet-visited range. Expected 4. BUG B: snapshot cursor misses it."
        )
        assert cursor.next() == 5

    def test_cursor_stop_iteration(self):
        tree = BTree(t=2)
        tree.insert(1)
        cursor = tree.cursor()
        cursor.next()
        with pytest.raises(StopIteration):
            cursor.next()
