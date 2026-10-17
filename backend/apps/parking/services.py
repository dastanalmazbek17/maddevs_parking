"""Shared clock and the window in which a booking holds its spot."""

from django.db.models import Q
from django.utils import timezone

from apps.bookings.models import BookingStatus
from apps.parking.constants import ENTRY_WINDOW
from apps.parking.exceptions import InvalidInterval


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
