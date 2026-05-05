"""
B-tree with in-order iterator that remains valid across concurrent modifications.

A B-tree of order `t` (minimum degree): each node holds between t-1 and 2t-1
keys. Supports insert, delete, search, and an in-order iteration cursor that
stays valid after inserts/deletes (it must iterate all keys that existed at
cursor creation and haven't been deleted, in sorted order).

Based on CLRS B-tree algorithms plus the "stable cursor" semantics from
database B-tree implementations (e.g., SQLite B-tree cursor).

Public API:
    tree = BTree(t=2)          # minimum degree 2 → 2-3-4 tree
    tree.insert(5)
    tree.insert(3)
    tree.delete(5)
    found = tree.search(3)     # True
    keys = list(tree)          # sorted list of all keys
    cursor = tree.cursor()     # positioned before first key
    cursor.next()              # advance; returns key or raises StopIteration
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class _Node:
    keys: list = field(default_factory=list)
    children: list = field(default_factory=list)

    @property
    def is_leaf(self) -> bool:
        return not self.children


class BTree:
    def __init__(self, t: int = 2):
        if t < 2:
            raise ValueError("minimum degree t must be >= 2")
        self.t = t
        self.root = _Node()

    # ── search ────────────────────────────────────────────────────────────────

    def search(self, key) -> bool:
        return self._search(self.root, key)

    def _search(self, node: _Node, key) -> bool:
        i = 0
        while i < len(node.keys) and key > node.keys[i]:
            i += 1
        if i < len(node.keys) and key == node.keys[i]:
            return True
        if node.is_leaf:
            return False
        return self._search(node.children[i], key)

    # ── insert ────────────────────────────────────────────────────────────────

    def insert(self, key) -> None:
        if self.search(key):
            return
        root = self.root
        if len(root.keys) == 2 * self.t - 1:
            new_root = _Node()
            new_root.children.append(self.root)
            self._split_child(new_root, 0)
            self.root = new_root
        self._insert_nonfull(self.root, key)

    def _insert_nonfull(self, node: _Node, key) -> None:
        i = len(node.keys) - 1
        if node.is_leaf:
            node.keys.append(None)
            while i >= 0 and key < node.keys[i]:
                node.keys[i + 1] = node.keys[i]
                i -= 1
            node.keys[i + 1] = key
        else:
            while i >= 0 and key < node.keys[i]:
                i -= 1
            i += 1
            if len(node.children[i].keys) == 2 * self.t - 1:
                self._split_child(node, i)
                if key > node.keys[i]:
                    i += 1
            self._insert_nonfull(node.children[i], key)

    def _split_child(self, parent: _Node, i: int) -> None:
        t = self.t
        y = parent.children[i]
        z = _Node()

        median = y.keys[t - 1]
        z.keys = y.keys[t:]
        y.keys = y.keys[:t - 1]

        if not y.is_leaf:
            z.children = y.children[t:]
            y.children = y.children[:t]

        parent.keys.insert(i, median)
        parent.children.insert(i + 1, z)

    # ── delete ────────────────────────────────────────────────────────────────

    def delete(self, key) -> None:
        if not self.search(key):
            raise KeyError(key)
        self._delete(self.root, key)
        if len(self.root.keys) == 0 and not self.root.is_leaf:
            self.root = self.root.children[0]

    def _delete(self, node: _Node, key) -> None:
        t = self.t
        i = 0
        while i < len(node.keys) and key > node.keys[i]:
            i += 1

        if i < len(node.keys) and node.keys[i] == key:
            if node.is_leaf:
                node.keys.pop(i)
            else:
                if len(node.children[i].keys) >= t:
                    # Replace with predecessor
                    pred = self._get_predecessor(node.children[i])
                    node.keys[i] = pred
                    self._delete(node.children[i], pred)
                elif len(node.children[i + 1].keys) >= t:
                    # Replace with successor
                    succ = self._get_successor(node.children[i + 1])
                    node.keys[i] = succ
                    self._delete(node.children[i + 1], succ)
                else:
                    # Merge children[i] and children[i+1]
                    self._merge(node, i)
                    self._delete(node.children[i], key)
        else:
            if node.is_leaf:
                return
            if len(node.children[i].keys) < t:
                self._fill(node, i)
                # After fill, key position may have shifted
                if i > len(node.keys):
                    i -= 1
            self._delete(node.children[i], key)

    def _get_predecessor(self, node: _Node):
        while not node.is_leaf:
            node = node.children[-1]
        return node.keys[-1]

    def _get_successor(self, node: _Node):
        while not node.is_leaf:
            node = node.children[0]
        return node.keys[0]

    def _merge(self, parent: _Node, i: int) -> None:
        left = parent.children[i]
        right = parent.children[i + 1]
        left.keys.append(parent.keys[i])
        left.keys.extend(right.keys)
        left.children.extend(right.children)
        parent.keys.pop(i)
        parent.children.pop(i + 1)

    def _fill(self, parent: _Node, i: int) -> None:
        t = self.t
        if i > 0 and len(parent.children[i - 1].keys) >= t:
            self._borrow_from_prev(parent, i)
        elif i < len(parent.children) - 1 and len(parent.children[i + 1].keys) >= t:
            self._borrow_from_next(parent, i)
        else:
            if i < len(parent.children) - 1:
                self._merge(parent, i)
            else:
                self._merge(parent, i - 1)

    def _borrow_from_prev(self, parent: _Node, i: int) -> None:
        child = parent.children[i]
        sibling = parent.children[i - 1]
        child.keys.insert(0, parent.keys[i - 1])
        if sibling.children:
            child.children.insert(0, sibling.children.pop())
        parent.keys[i - 1] = sibling.keys.pop()

    def _borrow_from_next(self, parent: _Node, i: int) -> None:
        child = parent.children[i]
        sibling = parent.children[i + 1]
        child.keys.append(parent.keys[i])
        if sibling.children:
            child.children.append(sibling.children.pop(0))
        parent.keys[i] = sibling.keys.pop(0)

    # ── iteration ─────────────────────────────────────────────────────────────

    def __iter__(self):
        """In-order traversal yielding all keys in sorted order."""
        yield from self._inorder(self.root)

    def _inorder(self, node: _Node):
        if node.is_leaf:
            yield from node.keys
        else:
            for i, child in enumerate(node.children):
                yield from self._inorder(child)
                if i < len(node.keys):
                    yield node.keys[i]

    def cursor(self) -> "BTreeCursor":
        return BTreeCursor(self)

    def __len__(self) -> int:
        return sum(1 for _ in self)

    # ── helpers for cursor ────────────────────────────────────────────────────

    def _min_key(self, node: _Node):
        """Return the smallest key in the subtree rooted at *node*, or None."""
        if node.is_leaf:
            return node.keys[0] if node.keys else None
        return self._min_key(node.children[0])

    def _min_greater_than(self, node: _Node, key):
        """Return the smallest key in the subtree rooted at *node* that is
        strictly greater than *key*, or None if no such key exists."""
        if node.is_leaf:
            for k in node.keys:
                if k > key:
                    return k
            return None
        i = 0
        while i < len(node.keys) and node.keys[i] <= key:
            i += 1
        res = self._min_greater_than(node.children[i], key)
        if res is not None:
            return res
        if i < len(node.keys):
            return node.keys[i]
        return None


class BTreeCursor:
    """
    Stable cursor for in-order traversal.

    The cursor follows the tree lazily so that deleted keys are skipped and
    newly inserted keys that fall in the not-yet-visited portion are included.
    """

    def __init__(self, tree: BTree):
        self._tree = tree
        self._last = None

    def _next_key(self):
        if self._last is None:
            return self._tree._min_key(self._tree.root)
        return self._tree._min_greater_than(self._tree.root, self._last)

    def next(self):
        key = self._next_key()
        if key is None:
            raise StopIteration
        self._last = key
        return key

    def has_next(self) -> bool:
        return self._next_key() is not None
