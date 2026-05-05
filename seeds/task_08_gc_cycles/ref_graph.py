"""
Reference-counted object graph with cycle detection.

Implements a simple reference counting memory manager. Objects may form
reference cycles (A → B → A), which pure refcounting cannot collect.

We add a mark-and-sweep cycle detector that runs when an object's refcount
drops to zero but the object is still reachable through cycles.

Based on: CPython's cyclic garbage collector (Objects/gcmodule.c)
The algorithm is a simplified version of the tricolor mark-and-sweep
described in the CPython developer's guide.

Key invariants:
  1. Objects with refcount > 0 must not be collected.
  2. Objects that are only reachable through cycles must be collected.
  3. Objects with __del__ (finalizers) in cycles are put in gc.garbage
     (not collected) — this matches CPython's behavior.

Public API:
    mgr = RefCountManager()
    a = mgr.alloc("A")
    b = mgr.alloc("B")
    mgr.add_ref(a, b)     # a holds reference to b
    mgr.add_ref(b, a)     # cycle: a ↔ b
    mgr.release(a)        # drop external reference to a
    mgr.release(b)        # drop external reference to b
    # now a and b are unreachable → cycle collector should free them
    assert mgr.is_collected(a)
    assert mgr.is_collected(b)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ManagedObject:
    name: str
    payload: Any = None
    refcount: int = 1             # starts at 1 (the creator holds a ref)
    refs: list["ManagedObject"] = field(default_factory=list)
    has_finalizer: bool = False   # if True, like __del__
    collected: bool = False

    def __repr__(self):
        return f"Obj({self.name}, rc={self.refcount})"


class RefCountManager:
    def __init__(self):
        self._objects: list[ManagedObject] = []
        self._garbage: list[ManagedObject] = []   # uncollectable (has finalizer)

    # ── public API ────────────────────────────────────────────────────────────

    def alloc(self, name: str, payload: Any = None, has_finalizer: bool = False) -> ManagedObject:
        obj = ManagedObject(name=name, payload=payload, has_finalizer=has_finalizer)
        self._objects.append(obj)
        return obj

    def add_ref(self, holder: ManagedObject, target: ManagedObject) -> None:
        """holder now holds a reference to target (increments target's refcount)."""
        holder.refs.append(target)
        target.refcount += 1

    def remove_ref(self, holder: ManagedObject, target: ManagedObject) -> None:
        """Remove one reference from holder to target (decrements target's refcount)."""
        holder.refs.remove(target)
        self._decref(target)

    def release(self, obj: ManagedObject) -> None:
        """Release the external reference to obj (caller no longer holds it)."""
        self._decref(obj)

    def collect(self) -> int:
        """
        Run cycle detection and collect unreachable cycles.
        Returns number of objects collected.

        Algorithm (CPython gc simplified):
        1. For each object, set gc_refs = refcount.
        2. For each object, subtract 1 from gc_refs for each ref it holds
           (simulate removing all internal references).
        3. Objects with gc_refs > 0 are still externally referenced → mark REACHABLE.
        4. From REACHABLE objects, mark all transitively reachable objects REACHABLE.
        5. Remaining objects (gc_refs == 0, not marked REACHABLE) are in cycles → collect.
        6. Objects with finalizers go to _garbage; others are freed.

        BUG A: Step 4 uses a simple BFS but starts from the wrong seed set.
        It starts from ALL objects with gc_refs > 0 rather than from only
        non-collected, non-cycle objects. This causes it to traverse from
        objects that are themselves part of cycles (if they were incremented
        by another cycle member in step 2 reduction).

        BUG B: Step 2 decrements gc_refs for each ref the object holds, but
        the current code decrements the HOLDER's gc_refs instead of the
        TARGET's gc_refs. This inverts the algorithm — objects that are
        referenced MORE end up with LOWER gc_refs.

        BUG C: Finalizer objects are put in _garbage but their refcounts are
        not zeroed and their internal refs are not cleared, so they keep their
        referents alive indefinitely (memory leak).
        """
        live = [o for o in self._objects if not o.collected]

        # Step 1: Set gc_refs = refcount
        gc_refs = {id(o): o.refcount for o in live}

        # Step 2: For each object, subtract 1 from each target's gc_refs
        # BUG B: decrements HOLDER instead of TARGET
        for o in live:
            for ref in o.refs:
                gc_refs[id(o)] -= 1    # BUG B: should be gc_refs[id(ref)] -= 1

        # Step 3 & 4: Mark reachable from objects with gc_refs > 0
        reachable: set[int] = set()
        worklist = [o for o in live if gc_refs[id(o)] > 0]
        # BUG A: worklist should only include objects with external refs
        # (gc_refs > 0 after step 2 subtractions mean external refs exist)
        # But BUG B corrupted gc_refs, so worklist is wrong.
        for start in worklist:
            stack = [start]
            while stack:
                obj = stack.pop()
                if id(obj) in reachable:
                    continue
                reachable.add(id(obj))
                for ref in obj.refs:
                    if id(ref) not in reachable:
                        stack.append(ref)

        # Step 5 & 6: Collect unreachable objects
        collected = 0
        for o in live:
            if id(o) not in reachable:
                if o.has_finalizer:
                    # BUG C: should clear o.refs to break the cycle
                    self._garbage.append(o)   # BUG C: refs not cleared → leak
                else:
                    o.collected = True
                    collected += 1

        return collected

    def is_collected(self, obj: ManagedObject) -> bool:
        return obj.collected

    @property
    def garbage(self) -> list[ManagedObject]:
        return list(self._garbage)

    # ── internal ──────────────────────────────────────────────────────────────

    def _decref(self, obj: ManagedObject) -> None:
        obj.refcount -= 1
        if obj.refcount == 0:
            # Clear all outgoing references (decrements their refcounts too)
            for ref in list(obj.refs):
                self._decref(ref)
            obj.refs.clear()
            obj.collected = True
        elif obj.refcount < 0:
            raise RuntimeError(f"refcount went negative for {obj}")
