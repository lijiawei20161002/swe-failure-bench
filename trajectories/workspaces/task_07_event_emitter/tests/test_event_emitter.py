"""Tests for EventEmitter. Run: pytest tests/ -x"""
import gc
import pytest
from event_emitter import EventEmitter


# ── basic on / emit / off ─────────────────────────────────────────────────────

class TestBasic:
    def test_on_and_emit(self):
        em = EventEmitter()
        received = []
        def handler(x):
            received.append(x)
        em.on("click", handler, weak=False)
        em.emit("click", 42)
        assert received == [42]

    def test_emit_returns_count(self):
        em = EventEmitter()
        def h(x): pass
        em.on("e", h, weak=False)
        em.on("e", h, weak=False)
        count = em.emit("e", 1)
        assert count == 2

    def test_off_removes_handler(self):
        em = EventEmitter()
        called = []
        def h(): called.append(True)
        em.on("e", h, weak=False)
        em.off("e", h)
        em.emit("e")
        assert called == []

    def test_off_nonexistent_is_noop(self):
        em = EventEmitter()
        def h(): pass
        em.off("no_such_event", h)   # must not raise

    def test_multiple_listeners(self):
        em = EventEmitter()
        log = []
        em.on("e", lambda: log.append("a"), weak=False)
        em.on("e", lambda: log.append("b"), weak=False)
        em.emit("e")
        assert sorted(log) == ["a", "b"]


# ── once ──────────────────────────────────────────────────────────────────────

class TestOnce:
    def test_once_fires_exactly_once(self):
        em = EventEmitter()
        called = []
        def h(): called.append(True)
        em.once("e", h, weak=False)
        em.emit("e")
        em.emit("e")
        assert len(called) == 1

    def test_once_removed_after_fire(self):
        em = EventEmitter()
        def h(): pass
        em.once("e", h, weak=False)
        em.emit("e")
        assert em.listener_count("e") == 0

    def test_on_and_once_together(self):
        em = EventEmitter()
        log = []
        em.on("e", lambda: log.append("on"), weak=False)
        em.once("e", lambda: log.append("once"), weak=False)
        em.emit("e")
        em.emit("e")
        assert log.count("on") == 2
        assert log.count("once") == 1


# ── wildcard matching ─────────────────────────────────────────────────────────

class TestWildcards:
    def test_single_star_one_segment(self):
        em = EventEmitter()
        log = []
        em.on("user.*", lambda e: log.append(e), weak=False)
        em.emit("user.login", "login")
        em.emit("user.logout", "logout")
        assert log == ["login", "logout"]

    def test_single_star_does_not_match_multiple_segments(self):
        em = EventEmitter()
        log = []
        em.on("user.*", lambda e: log.append(e), weak=False)
        em.emit("user.login.extra", "should-not-match")
        assert log == []

    def test_double_star_matches_multiple_segments(self):
        em = EventEmitter()
        log = []
        em.on("order.**", lambda e: log.append(e), weak=False)
        em.emit("order.created", "created")
        em.emit("order.payment.done", "payment-done")
        assert "created" in log
        assert "payment-done" in log

    def test_double_star_matches_zero_extra_segments(self):
        """'order.**' should match 'order' itself (zero trailing segments)."""
        em = EventEmitter()
        log = []
        em.on("order.**", lambda e: log.append(e), weak=False)
        em.emit("order", "base")
        assert "base" in log

    def test_exact_match_still_works(self):
        em = EventEmitter()
        log = []
        em.on("click", lambda: log.append("click"), weak=False)
        em.emit("click")
        assert log == ["click"]

    def test_wildcard_and_exact_both_fire(self):
        em = EventEmitter()
        log = []
        em.on("user.*", lambda e: log.append("wildcard"), weak=False)
        em.on("user.login", lambda e: log.append("exact"), weak=False)
        em.emit("user.login", "data")
        assert "wildcard" in log
        assert "exact" in log


# ── error isolation ───────────────────────────────────────────────────────────

class TestErrorIsolation:
    def test_exception_does_not_stop_other_handlers(self):
        em = EventEmitter()
        log = []

        def bad(): raise RuntimeError("boom")
        def good(): log.append("ok")

        em.on("e", bad, weak=False)
        em.on("e", good, weak=False)
        em.emit("e")
        assert "ok" in log, "good handler must run despite bad handler raising"

    def test_errors_collected(self):
        em = EventEmitter()
        def bad(): raise ValueError("oops")
        em.on("e", bad, weak=False)
        em.emit("e")
        errors = em.clear_errors()
        assert len(errors) == 1
        assert isinstance(errors[0], ValueError)

    def test_multiple_errors_all_collected(self):
        em2 = EventEmitter()
        def make_bad(msg):
            def bad(): raise ValueError(msg)
            return bad
        em2.on("e", make_bad("1"), weak=False)
        em2.on("e", make_bad("2"), weak=False)
        em2.on("e", make_bad("3"), weak=False)
        em2.emit("e")
        errors = em2.clear_errors()
        assert len(errors) == 3


# ── weak references ───────────────────────────────────────────────────────────

class TestWeakRefs:
    def test_dead_weakref_not_called(self):
        em = EventEmitter()
        log = []

        class Obj:
            def handler(self):
                log.append(True)

        obj = Obj()
        em.on("e", obj.handler, weak=True)
        del obj
        gc.collect()
        em.emit("e")
        assert log == [], "dead weakref handler must not be called"

    def test_live_weakref_called(self):
        em = EventEmitter()
        log = []

        class Obj:
            def handler(self):
                log.append(True)

        obj = Obj()
        em.on("e", obj.handler, weak=True)
        em.emit("e")
        assert log == [True]
        del obj   # cleanup
