"""Shared clock for parking services."""

from django.utils import timezone

from apps.parking.exceptions import InvalidInterval


def resolve_now(now):
    if now is None:
        now = timezone.now()
    if now.tzinfo is None or now.utcoffset() is None:
        raise InvalidInterval("now must be timezone-aware.")
    return now
