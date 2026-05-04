"""
Rope — a binary tree data structure for efficient string manipulation.

Each leaf stores a string chunk. Internal nodes track the total weight
(length) of the left subtree, enabling O(log n) index, split, and concat.

Based on: Boehm, Atkinson & Plass (1995) "Ropes: an Alternative to Strings"
Used in: text editors (xi-editor, Emacs gap buffer alternative), code editors.

Public API:
    r = Rope("Hello, World!")
    r2 = r.concat(Rope(" Goodbye!"))
    left, right = r2.split(7)   # split after index 7
    r2.index(0)                  # → 'H'
    str(r2)                      # → full string
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class _Node:
    weight: int = 0            # length of left subtree (or string if leaf)
    value: Optional[str] = None  # non-None ↔ leaf
    left: Optional["_Node"] = None
    right: Optional["_Node"] = None


_MAX_LEAF = 8   # split leaves larger than this for balance


def _leaf(s: str) -> _Node:
    return _Node(weight=len(s), value=s)


def _internal(left: _Node, right: _Node) -> _Node:
    return _Node(weight=_total_weight(left), left=left, right=right)


def _total_weight(node: Optional[_Node]) -> int:
    if node is None:
        return 0
    if node.value is not None:
        return node.weight            # leaf: weight == len(value)
    return node.weight + _total_weight(node.right)


class Rope:
    """Immutable rope. All operations return new Rope objects."""

    def __init__(self, s: str = ""):
        if len(s) <= _MAX_LEAF:
            self._root = _leaf(s)
        else:
            mid = len(s) // 2
            self._root = _internal(Rope(s[:mid])._root, Rope(s[mid:])._root)

    @classmethod
    def _from_node(cls, node: _Node) -> "Rope":
        r = cls.__new__(cls)
        r._root = node
        return r

    # ── primitive ops ─────────────────────────────────────────────────────────

    def __len__(self) -> int:
        return _total_weight(self._root)

    def __str__(self) -> str:
        parts: list[str] = []
        _collect(self._root, parts)
        return "".join(parts)

    def index(self, i: int) -> str:
        """Return the character at position *i* (0-based)."""
        if i < 0 or i >= len(self):
            raise IndexError(f"rope index {i} out of range [0, {len(self)})")
        return _index(self._root, i)

    def concat(self, other: "Rope") -> "Rope":
        """Return a new Rope that is self + other."""
        node = _internal(self._root, other._root)
        return Rope._from_node(node)

    def split(self, i: int) -> tuple["Rope", "Rope"]:
        """
        Split rope at position *i* (0-based).
        Returns (left, right) where left has chars [0, i) and right [i, end).
        """
        if i < 0 or i > len(self):
            raise IndexError(f"split index {i} out of range [0, {len(self)}]")
        left_node, right_node = _split(self._root, i)
        return Rope._from_node(left_node), Rope._from_node(right_node)

    def __getitem__(self, key) -> "Rope":
        if isinstance(key, slice):
            start, stop, step = key.indices(len(self))
            if step != 1:
                raise NotImplementedError("step != 1 not supported")
            _, right = self.split(start)
            left, _ = right.split(stop - start)
            return left
        return Rope(self.index(key))

    def __add__(self, other: "Rope") -> "Rope":
        return self.concat(other)

    def __repr__(self) -> str:
        return f"Rope({str(self)!r})"


# ── internal helpers ──────────────────────────────────────────────────────────

def _collect(node: Optional[_Node], out: list[str]) -> None:
    if node is None:
        return
    if node.value is not None:
        out.append(node.value)
        return
    _collect(node.left, out)
    _collect(node.right, out)


def _index(node: _Node, i: int) -> str:
    while node.value is None:
        if i < node.weight:
            node = node.left
        else:
            i -= node.weight
            node = node.right
    return node.value[i]


def _split(node: _Node, i: int) -> tuple[_Node, _Node]:
    """Split node at byte-offset *i*. Returns (left_node, right_node)."""
    if node.value is not None:
        # Leaf split
        left_str = node.value[:i]
        right_str = node.value[i:]
        return (
            _leaf(left_str) if left_str else _leaf(""),
            _leaf(right_str) if right_str else _leaf(""),
        )

    if i == node.weight:
        return (
            node.left if node.left is not None else _leaf(""),
            node.right if node.right is not None else _leaf(""),
        )

    if i < node.weight:
        ll, lr = _split(node.left, i)
        right = _internal(lr, node.right) if node.right else lr
        return ll, right
    else:
        rl, rr = _split(node.right, i - node.weight)
        left = _internal(node.left, rl) if node.left else rl
        return left, rr
