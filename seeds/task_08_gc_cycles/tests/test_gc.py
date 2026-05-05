"""Tests for reference-counted GC with cycle detection. Run: pytest tests/ -x"""
import pytest
from ref_graph import RefCountManager, ManagedObject


# ── basic refcounting ─────────────────────────────────────────────────────────

class TestRefCounting:
    def test_alloc_refcount_one(self):
        mgr = RefCountManager()
        a = mgr.alloc("a")
        assert a.refcount == 1

    def test_add_ref_increments(self):
        mgr = RefCountManager()
        a = mgr.alloc("a")
        b = mgr.alloc("b")
        mgr.add_ref(a, b)
        assert b.refcount == 2

    def test_release_collects_unreachable(self):
        mgr = RefCountManager()
        a = mgr.alloc("a")
        mgr.release(a)
        assert mgr.is_collected(a)

    def test_held_object_not_collected(self):
        mgr = RefCountManager()
        a = mgr.alloc("a")
        b = mgr.alloc("b")
        mgr.add_ref(a, b)
        mgr.release(b)   # drop external ref, but a still holds b
        assert not mgr.is_collected(b), "b is still referenced by a"

    def test_releasing_holder_cascades(self):
        mgr = RefCountManager()
        a = mgr.alloc("a")
        b = mgr.alloc("b")
        mgr.add_ref(a, b)
        mgr.release(b)   # b.rc = 1 (still held by a)
        mgr.release(a)   # a.rc = 0 → collected → b.rc drops to 0 → collected
        assert mgr.is_collected(a)
        assert mgr.is_collected(b), "b should be cascade-collected when a is released"


# ── cycle detection (BUG A, B) ────────────────────────────────────────────────

class TestCycleDetection:
    def test_simple_cycle_collected(self):
        """
        Two objects forming a cycle, with no external references, must
        be collected by collect().
        """
        mgr = RefCountManager()
        a = mgr.alloc("a")
        b = mgr.alloc("b")
        mgr.add_ref(a, b)   # a → b  (b.rc=2)
        mgr.add_ref(b, a)   # b → a  (a.rc=2)
        mgr.release(a)      # external ref dropped (a.rc=1, still in cycle)
        mgr.release(b)      # external ref dropped (b.rc=1, still in cycle)

        n = mgr.collect()
        assert n == 2, f"Expected 2 objects collected, got {n}"
        assert mgr.is_collected(a), (
            "a should be collected — it's only reachable via cycle. "
            "BUG B: if gc_refs subtraction is inverted, a appears externally referenced."
        )
        assert mgr.is_collected(b), "b should be collected"

    def test_asymmetric_refs_cycle_collected(self):
        """
        BUG B is exposed by asymmetric reference counts.
        x holds refs to [y, z]; y and z each hold ref to x.
        No external refs → entire cluster is cyclic garbage.

        Correct step-2 subtracts gc_refs of TARGETS:
          x.gc_refs starts at 2 (x+y hold refs to x... wait)

        Let's set up: external creates x, y, z (each rc=1).
        x → y, x → z, y → x, z → x.
        After release all: x.rc=2 (from y,z), y.rc=1 (from x), z.rc=1 (from x)

        Correct gc_refs after step 2:
          x.refs=[y,z]: gc_refs[y]-=1, gc_refs[z]-=1
          y.refs=[x]:   gc_refs[x]-=1
          z.refs=[x]:   gc_refs[x]-=1
          Result: gc_refs = {x:0, y:0, z:0} → collect all 3

        BUG B (decrement holder):
          x.refs=[y,z]: gc_refs[x]-=1, gc_refs[x]-=1 → gc_refs[x] = 0 (2-2=0)
          y.refs=[x]:   gc_refs[y]-=1 → gc_refs[y] = 0
          z.refs=[x]:   gc_refs[z]-=1 → gc_refs[z] = 0
          Coincidentally same result (by symmetry of total degrees)

        Asymmetric case to expose BUG B: x has refs=[y], y has refs=[], no cycle.
        Plus a detached cycle a↔b.

        More reliable: use a case where an externally-referenced object
        holds MANY refs — BUG B causes it to appear unreferenced.
        """
        mgr = RefCountManager()
        # External root holds multiple refs (should not be collected)
        root = mgr.alloc("root")
        a = mgr.alloc("a")
        b = mgr.alloc("b")
        c = mgr.alloc("c")
        mgr.add_ref(root, a)
        mgr.add_ref(root, b)   # root has 2 outgoing refs
        mgr.add_ref(root, c)   # root has 3 outgoing refs
        mgr.release(a)
        mgr.release(b)
        mgr.release(c)
        # root still externally held: root.rc=1, a.rc=1(root), b.rc=1(root), c.rc=1(root)

        # Correct: root has gc_refs=1 (external), a/b/c all reachable → nothing collected
        # BUG B: root has 3 refs → gc_refs[root] decremented 3 times → goes to -2 or 0
        n = mgr.collect()
        assert n == 0, (
            f"No objects should be collected — all reachable from external root. "
            f"Got {n} collected. BUG B: objects with many outgoing refs appear "
            "unreachable because the holder's gc_refs is over-decremented."
        )
        assert not mgr.is_collected(root)
        assert not mgr.is_collected(a)
        assert not mgr.is_collected(b)
        assert not mgr.is_collected(c)

    def test_three_node_cycle_collected(self):
        """A→B→C→A cycle with no external refs must all be collected."""
        mgr = RefCountManager()
        a = mgr.alloc("a")
        b = mgr.alloc("b")
        c = mgr.alloc("c")
        mgr.add_ref(a, b)
        mgr.add_ref(b, c)
        mgr.add_ref(c, a)
        mgr.release(a)
        mgr.release(b)
        mgr.release(c)

        n = mgr.collect()
        assert n == 3, f"Expected 3 collected, got {n}"
        assert all(mgr.is_collected(o) for o in [a, b, c])

    def test_externally_referenced_cycle_not_collected(self):
        """
        If a cycle member has an external reference, NONE of the cycle is collected.
        """
        mgr = RefCountManager()
        a = mgr.alloc("a")
        b = mgr.alloc("b")
        mgr.add_ref(a, b)
        mgr.add_ref(b, a)
        mgr.release(b)   # only b's external ref dropped; a still externally held

        n = mgr.collect()
        assert n == 0, "Neither a nor b should be collected — a has external ref"
        assert not mgr.is_collected(a)
        assert not mgr.is_collected(b)

    def test_mixed_reachable_and_cycle(self):
        """
        Objects reachable from external root must not be collected even if
        they're also part of a cycle structure.

        External: root → a → b ↔ c (b and c form a cycle, but a holds b)
        """
        mgr = RefCountManager()
        root = mgr.alloc("root")
        a = mgr.alloc("a")
        b = mgr.alloc("b")
        c = mgr.alloc("c")
        mgr.add_ref(root, a)
        mgr.add_ref(a, b)
        mgr.add_ref(b, c)
        mgr.add_ref(c, b)   # cycle: b ↔ c, but reachable from root
        mgr.release(a)
        mgr.release(b)
        mgr.release(c)
        # root still holds external reference

        n = mgr.collect()
        assert n == 0, "No objects should be collected — all reachable from root"

    def test_detached_cycle_while_other_object_live(self):
        """Isolated cycle gets collected; live object is untouched."""
        mgr = RefCountManager()
        live = mgr.alloc("live")   # externally held throughout
        a = mgr.alloc("a")
        b = mgr.alloc("b")
        mgr.add_ref(a, b)
        mgr.add_ref(b, a)
        mgr.release(a)
        mgr.release(b)

        n = mgr.collect()
        assert n == 2, f"Isolated cycle (a, b) should be collected, got {n}"
        assert not mgr.is_collected(live), "live object must not be collected"


# ── finalizer handling (BUG C) ────────────────────────────────────────────────

class TestFinalizers:
    def test_cycle_with_finalizer_goes_to_garbage(self):
        """
        Objects with finalizers in cycles go to gc.garbage (uncollectable),
        matching CPython's behavior.
        """
        mgr = RefCountManager()
        a = mgr.alloc("a", has_finalizer=True)
        b = mgr.alloc("b")
        mgr.add_ref(a, b)
        mgr.add_ref(b, a)
        mgr.release(a)
        mgr.release(b)

        mgr.collect()
        assert not mgr.is_collected(a), "Finalizer object should not be auto-collected"
        assert a in mgr.garbage, "Finalizer object should be in garbage list"

    def test_finalizer_object_refs_cleared(self):
        """
        BUG C: finalizer objects put in garbage must have their internal refs
        cleared, otherwise they keep their referents alive indefinitely.
        After collect(), a's refs should be cleared (or a's referents' refcounts
        reduced), so b can be freed.
        """
        mgr = RefCountManager()
        a = mgr.alloc("a", has_finalizer=True)
        b = mgr.alloc("b")   # no finalizer
        c = mgr.alloc("c")   # no finalizer
        mgr.add_ref(a, b)    # a holds b
        mgr.add_ref(a, c)    # a holds c
        mgr.add_ref(b, a)    # cycle
        mgr.release(a)
        mgr.release(b)
        mgr.release(c)

        mgr.collect()
        # b and c are not in the cycle's finalized set but they should be
        # freed once a's refs are cleared. Check that b.refcount == 0 or b is collected.
        assert b.refcount == 0 or mgr.is_collected(b), (
            f"b (rc={b.refcount}) should be freed after a's refs are cleared. "
            "BUG C: finalizer object refs not cleared → b kept alive by a forever."
        )

    def test_non_finalizer_cycle_still_collected(self):
        """Cycles with no finalizers are always collected, finalizer rule only applies to the finalizer objects."""
        mgr = RefCountManager()
        x = mgr.alloc("x")
        y = mgr.alloc("y")
        mgr.add_ref(x, y)
        mgr.add_ref(y, x)
        mgr.release(x)
        mgr.release(y)
        n = mgr.collect()
        assert n == 2
