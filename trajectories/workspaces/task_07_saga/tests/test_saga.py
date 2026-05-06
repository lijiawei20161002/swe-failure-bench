"""
Tests for the saga orchestrator.
Run: pip install pytest && pytest tests/ -x -q
"""
import pytest
import booking
from saga import Saga
from orchestrator import SagaOrchestrator


@pytest.fixture(autouse=True)
def reset_state():
    booking._reset()
    yield
    booking._reset()


def make_trip_saga():
    return (
        Saga("book-trip")
        .step("reserve-flight",  booking.reserve_flight,  booking.cancel_flight)
        .step("reserve-hotel",   booking.reserve_hotel,   booking.cancel_hotel)
        .step("charge-payment",  booking.charge_payment,  booking.refund_payment)
    )


class TestSuccessPath:
    def test_all_steps_complete(self):
        saga = make_trip_saga()
        ctx = {"flight": "AA123", "hotel": "Grand Hotel", "amount_cents": 45000}
        result = SagaOrchestrator().run(saga, ctx)
        assert result.success
        assert "reservation_id" in ctx
        assert "booking_id" in ctx
        assert "charge_id" in ctx

    def test_reservations_created(self):
        saga = make_trip_saga()
        ctx = {}
        SagaOrchestrator().run(saga, ctx)
        assert ctx["reservation_id"] in booking._reservations
        assert ctx["booking_id"] in booking._hotel_bookings
        assert ctx["charge_id"] in booking._charges

    def test_result_has_context(self):
        saga = make_trip_saga()
        result = SagaOrchestrator().run(saga, {})
        assert result.context is not None


class TestFirstStepFails:
    def test_no_compensation_needed(self):
        """If step 1 fails, nothing was created so nothing to undo."""
        def fail_immediately(ctx):
            raise RuntimeError("flight unavailable")

        saga = (
            Saga("fail-early")
            .step("reserve-flight", fail_immediately, booking.cancel_flight)
            .step("reserve-hotel",  booking.reserve_hotel, booking.cancel_hotel)
        )
        result = SagaOrchestrator().run(saga, {})
        assert not result.success
        assert result.failed_step == "reserve-flight"
        assert result.compensations_run == []


class TestCompensationOrdering:
    """
    Core correctness: when a saga step fails, compensations must run in
    REVERSE order of the original steps.

    In the travel booking workflow:
      Step 1: reserve_flight  → creates reservation record (anchor for all)
      Step 2: reserve_hotel   → linked to the reservation record
      Step 3: charge_payment  → fails (payment declined)

    Correct compensation order (reverse):
      Compensate step 2 first: cancel_hotel   (still has reservation record)
      Compensate step 1 last:  cancel_flight  (deletes reservation record)

    Wrong compensation order (forward — the bug):
      Compensate step 1 first: cancel_flight  (deletes reservation record)
      Compensate step 2 next:  cancel_hotel   (FAILS — reservation gone!)

    The BUG is in orchestrator.py: `for step in completed` iterates in
    forward order.  Fix: `for step in reversed(completed)`.
    """

    def test_payment_failure_compensates_in_reverse_order(self):
        """
        When payment is declined, hotel and flight compensations must run
        in reverse order (hotel first, then flight).
        """
        saga = make_trip_saga()
        ctx = {"decline_payment": True}
        result = SagaOrchestrator().run(saga, ctx)

        assert not result.success
        assert result.failed_step == "charge-payment"

        # Compensations must have run without error
        failed_comps = [c for c in result.compensations_run if "FAILED" in c]
        assert not failed_comps, (
            f"Compensation(s) failed: {failed_comps}. "
            "This happens when compensations run in forward order: "
            "cancel_flight deletes the reservation before cancel_hotel "
            "can use it to look up the check-in date. "
            "Fix: iterate `reversed(completed)` in the orchestrator."
        )

    def test_payment_failure_leaves_no_reservations(self):
        """After a failed saga with successful compensation, state is clean."""
        saga = make_trip_saga()
        ctx = {"decline_payment": True}
        result = SagaOrchestrator().run(saga, ctx)

        assert not result.success
        # If compensation succeeded, all records must be gone
        failed = [c for c in result.compensations_run if "FAILED" in c]
        if not failed:
            assert len(booking._reservations) == 0
            assert len(booking._hotel_bookings) == 0

    def test_compensation_order_is_reverse(self):
        """
        Explicitly verify compensation runs in reverse step order.
        Uses a recording fixture to capture execution order.
        """
        order = []

        def step_a(ctx): order.append("do-A")
        def step_b(ctx): order.append("do-B")
        def step_c(ctx): raise RuntimeError("C fails")
        def undo_a(ctx): order.append("undo-A")
        def undo_b(ctx): order.append("undo-B")
        def undo_c(ctx): order.append("undo-C")  # never called (C failed)

        saga = (
            Saga("ordering-test")
            .step("A", step_a, undo_a)
            .step("B", step_b, undo_b)
            .step("C", step_c, undo_c)
        )
        SagaOrchestrator().run(saga, {})

        assert order == ["do-A", "do-B", "undo-B", "undo-A"], (
            f"Expected order [do-A, do-B, undo-B, undo-A], got {order}. "
            "Compensations must run in reverse order (B before A). "
            "The orchestrator is iterating `completed` forward instead of "
            "`reversed(completed)`."
        )

    def test_two_step_failure_order(self):
        """Compensation of 2 completed steps runs in reverse."""
        order = []

        def do(name):
            def action(ctx): order.append(f"do-{name}")
            return action

        def undo(name):
            def comp(ctx): order.append(f"undo-{name}")
            return comp

        def fail(ctx): raise RuntimeError("boom")

        saga = (
            Saga("two-step")
            .step("X", do("X"), undo("X"))
            .step("Y", do("Y"), undo("Y"))
            .step("Z", fail,    undo("Z"))
        )
        SagaOrchestrator().run(saga, {})
        assert order == ["do-X", "do-Y", "undo-Y", "undo-X"], (
            f"Got {order}"
        )

    def test_single_step_failure_no_compensation(self):
        order = []

        def fail(ctx): raise RuntimeError("step 1 fails")
        def undo(ctx): order.append("undo")

        saga = Saga("one-fail").step("X", fail, undo)
        result = SagaOrchestrator().run(saga, {})
        assert not result.success
        assert order == []   # nothing completed, nothing to compensate

    def test_successful_saga_runs_no_compensations(self):
        saga = make_trip_saga()
        result = SagaOrchestrator().run(saga, {})
        assert result.success
        assert result.compensations_run == []
