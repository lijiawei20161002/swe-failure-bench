"""
Tests for ErrorAggregator.
Run: pip install pytest && pytest tests/ -x -q
"""
import gc
import sys
import weakref
import pytest
from error_aggregator import ErrorAggregator


class TestBasicCapture:
    def test_captures_exception(self):
        agg = ErrorAggregator()
        with agg.capture("op1"):
            raise ValueError("something broke")
        assert len(agg) == 1

    def test_no_capture_on_success(self):
        agg = ErrorAggregator()
        with agg.capture("op1"):
            pass
        assert len(agg) == 0

    def test_captures_multiple(self):
        agg = ErrorAggregator()
        with agg.capture("a"):
            raise ValueError("a broke")
        with agg.capture("b"):
            raise RuntimeError("b broke")
        assert len(agg) == 2

    def test_report_contains_label_and_message(self):
        agg = ErrorAggregator()
        with agg.capture("myop"):
            raise TypeError("bad type")
        lines = agg.report()
        assert len(lines) == 1
        assert "myop" in lines[0]
        assert "bad type" in lines[0]

    def test_continues_after_failure(self):
        """capture() should not re-raise; batch continues."""
        results = []
        agg = ErrorAggregator()
        for i in range(3):
            with agg.capture(f"op{i}"):
                if i == 1:
                    raise ValueError("middle fails")
                results.append(i)
        assert results == [0, 2]
        assert len(agg) == 1

    def test_clear_discards_errors(self):
        agg = ErrorAggregator()
        with agg.capture("x"):
            raise ValueError("x")
        agg.clear()
        assert len(agg) == 0


class TestMemoryLeak:
    """
    Core correctness test: captured exceptions must NOT keep objects alive.

    When ErrorAggregator.capture() catches an exception, it calls
    sys.exc_info() which returns (type, value, traceback). The traceback
    object chains through every frame on the call stack at the point of
    the exception via tb.tb_frame. Each frame holds its local variables.

    If the aggregator stores the raw traceback, any object that was a
    local variable in the failing call (or any of its callers) will stay
    alive as long as the aggregator lives — even after the caller has
    released all its references.

    The fix: extract what you need from the traceback immediately, then
    store only the formatted string (or set the tb slot to None), so the
    frame chain is released.
    """

    def test_objects_in_failing_frame_are_collected(self):
        """
        An object referenced only inside the failing function must be
        garbage-collected after capture() returns, not kept alive by the
        stored traceback.
        """
        collected = []

        class Tracked:
            def __del__(self):
                collected.append("collected")

        agg = ErrorAggregator()

        def failing_op():
            # obj is a local variable in this frame.
            # If the traceback is stored, this frame stays alive → obj stays alive.
            obj = Tracked()
            ref = weakref.ref(obj)
            raise ValueError("boom")

        with agg.capture("op"):
            failing_op()

        # Force collection
        gc.collect()
        gc.collect()

        assert len(collected) == 1, (
            "Object inside the failing frame was not garbage-collected. "
            "The ErrorAggregator is keeping the traceback object alive, "
            "which retains the entire frame chain and all frame locals. "
            "Fix: do not store the raw traceback — convert to a formatted "
            "string with traceback.format_tb() or set the tb slot to None."
        )

    def test_aggregator_itself_does_not_keep_caller_alive(self):
        """
        The caller that invokes capture() should be collectable after
        the with-block exits, even if an exception was raised inside it.
        """
        collected = []

        class Caller:
            def run(self, agg):
                with agg.capture("step"):
                    raise RuntimeError("caller error")

            def __del__(self):
                collected.append("caller gone")

        agg = ErrorAggregator()
        caller = Caller()
        caller.run(agg)
        del caller

        gc.collect()
        gc.collect()

        assert len(collected) == 1, (
            "The Caller object was not collected after del. "
            "Its frame is still referenced via the stored traceback."
        )

    def test_multiple_captures_release_frames(self):
        """All frame chains from multiple captures must be released."""
        alive = []

        class Resource:
            def __init__(self, name):
                self.name = name
            def __del__(self):
                alive.append(self.name)

        agg = ErrorAggregator()

        def op(name):
            r = Resource(name)
            raise ValueError(f"{name} failed")

        for name in ["A", "B", "C"]:
            with agg.capture(name):
                op(name)

        gc.collect()
        gc.collect()

        assert len(alive) == 3, (
            f"Expected 3 Resources collected, got {len(alive)}: {alive}. "
            "Stored tracebacks are keeping frame locals alive."
        )

    def test_report_still_works_after_fix(self):
        """report() must still return useful info after the traceback is released."""
        agg = ErrorAggregator()
        with agg.capture("myop"):
            raise TypeError("bad input")
        lines = agg.report()
        assert "myop" in lines[0]
        assert "TypeError" in lines[0]
        assert "bad input" in lines[0]
