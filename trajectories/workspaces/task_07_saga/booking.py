"""
Concrete saga steps for a travel-booking workflow.

Booking a trip requires three steps in order:
  1. reserve_flight   — creates a flight reservation, returns reservation_id
  2. reserve_hotel    — creates a hotel booking *linked to* the flight
                        reservation (hotels need the flight arrival time
                        stored on the reservation to set check-in date)
  3. charge_payment   — charges the customer's card

Compensations must run in reverse:
  3. refund_payment   — refunds the charge (if it was made)
  2. cancel_hotel     — cancels the hotel booking (uses reservation_id)
  1. cancel_flight    — deletes the flight reservation

If cancel_flight runs BEFORE cancel_hotel, the hotel cancellation fails
because it needs the reservation record (which stores check-in date) to
issue the cancellation to the hotel's API.  The reservation is the anchor
for the entire booking.

This is a realistic dependency: hotel APIs often require the original
booking reference to cancel.
"""
from __future__ import annotations


class BookingError(Exception):
    pass


# ── simulated external state ──────────────────────────────────────────────────

_reservations: dict[str, dict] = {}     # reservation_id → reservation data
_hotel_bookings: dict[str, dict] = {}   # booking_id → booking data
_charges: dict[str, int] = {}           # charge_id → amount_cents


def _reset():
    """Clear all state — used between tests."""
    _reservations.clear()
    _hotel_bookings.clear()
    _charges.clear()


# ── step 1: flight reservation ────────────────────────────────────────────────

def reserve_flight(ctx: dict) -> None:
    """
    Reserve a flight.  Stores reservation_id and arrival_time in ctx.
    The arrival_time is needed by reserve_hotel.
    """
    reservation_id = f"RES-{len(_reservations) + 1:04d}"
    arrival_time = ctx.get("arrival_time", "2026-06-15T14:00")
    _reservations[reservation_id] = {
        "flight": ctx.get("flight", "AA123"),
        "arrival_time": arrival_time,
        "status": "active",
    }
    ctx["reservation_id"] = reservation_id


def cancel_flight(ctx: dict) -> None:
    """
    Cancel a flight reservation.  Removes it from the reservation store.
    Must run AFTER cancel_hotel because cancel_hotel needs the reservation
    record to look up the check-in date for the hotel API call.
    """
    reservation_id = ctx.get("reservation_id")
    if not reservation_id or reservation_id not in _reservations:
        raise BookingError(
            f"Cannot cancel flight: reservation {reservation_id!r} not found. "
            "Was cancel_flight called before cancel_hotel? "
            "cancel_hotel requires the reservation record to be present."
        )
    del _reservations[reservation_id]


# ── step 2: hotel booking ─────────────────────────────────────────────────────

def reserve_hotel(ctx: dict) -> None:
    """
    Book a hotel room.  Uses reservation_id to fetch the arrival_time
    (check-in date) from the flight reservation record.
    """
    reservation_id = ctx.get("reservation_id")
    if not reservation_id or reservation_id not in _reservations:
        raise BookingError("Cannot book hotel: no active flight reservation")

    arrival_time = _reservations[reservation_id]["arrival_time"]
    booking_id = f"HTL-{len(_hotel_bookings) + 1:04d}"
    _hotel_bookings[booking_id] = {
        "reservation_id": reservation_id,
        "hotel": ctx.get("hotel", "Grand Hotel"),
        "check_in": arrival_time,
        "status": "confirmed",
    }
    ctx["booking_id"] = booking_id


def cancel_hotel(ctx: dict) -> None:
    """
    Cancel a hotel booking.  Needs the reservation record to look up
    check-in date for the hotel's cancellation API (hotels require the
    original check-in date to process a cancellation).
    """
    booking_id = ctx.get("booking_id")
    reservation_id = ctx.get("reservation_id")

    if not booking_id or booking_id not in _hotel_bookings:
        return   # hotel was never booked — nothing to cancel

    # Hotel API requires check-in date from the flight reservation
    if not reservation_id or reservation_id not in _reservations:
        raise BookingError(
            f"Cannot cancel hotel {booking_id!r}: reservation "
            f"{reservation_id!r} not found. "
            "The hotel cancellation API needs the check-in date, which is "
            "stored on the flight reservation. If cancel_flight ran first, "
            "the reservation record is gone and this call fails."
        )

    del _hotel_bookings[booking_id]


# ── step 3: payment ───────────────────────────────────────────────────────────

def charge_payment(ctx: dict) -> None:
    """Charge the customer. Raises PaymentDeclined to simulate failure."""
    if ctx.get("decline_payment"):
        raise BookingError("Payment declined")
    charge_id = f"CHG-{len(_charges) + 1:04d}"
    amount = ctx.get("amount_cents", 50000)
    _charges[charge_id] = amount
    ctx["charge_id"] = charge_id


def refund_payment(ctx: dict) -> None:
    """Refund a payment charge."""
    charge_id = ctx.get("charge_id")
    if charge_id and charge_id in _charges:
        del _charges[charge_id]
