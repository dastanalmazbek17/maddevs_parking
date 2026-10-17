"""Spot state derived from visits and bookings. Nothing is stored on the spot."""

from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from apps.bookings.models import Booking, BookingStatus
from apps.parking.constants import ENTRY_WINDOW
from apps.parking.exceptions import InvalidInterval
from apps.parking.models import Spot
from apps.visits.models import Visit

OCCUPIED = "occupied"
BOOKED = "booked"
FREE = "free"


def resolve_now(now):
    if now is None:
        now = timezone.now()
    if now.tzinfo is None or now.utcoffset() is None:
        raise InvalidInterval("now must be timezone-aware.")
    return now


def booking_holds_spot_q(now):
    """Active booking whose entry window covers `now`, including 15 minutes early.

    The spot is held while `starts_at - 15 minutes <= now < starts_at + 15 minutes`.
    That is the same condition for the map and for walk-in selection.
    """

    return Q(
        status=BookingStatus.ACTIVE,
        starts_at__gt=now - ENTRY_WINDOW,
        starts_at__lte=now + ENTRY_WINDOW,
    )


def spot_statuses(*, now=None):
    """Return every spot as `(spot, occupied|booked|free)`, ordered by pk."""

    now = resolve_now(now)
    active_visit = Visit.objects.filter(spot=OuterRef("pk"), exited_at__isnull=True)
    held_booking = Booking.objects.filter(spot=OuterRef("pk")).filter(booking_holds_spot_q(now))
    spots = Spot.objects.annotate(
        has_visit=Exists(active_visit),
        has_hold=Exists(held_booking),
    ).order_by("pk")
    result = []
    for spot in spots:
        if spot.has_visit:
            state = OCCUPIED
        elif spot.has_hold:
            state = BOOKED
        else:
            state = FREE
        result.append((spot, state))
    return result
