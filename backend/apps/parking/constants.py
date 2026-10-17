"""Shared parking rules. Services must not hard-code these durations."""

from datetime import timedelta

ENTRY_WINDOW = timedelta(minutes=15)
BOOKING_START_GRACE = timedelta(minutes=1)
MIN_BOOKING_DURATION = timedelta(minutes=15)
MAX_BOOKING_DURATION = timedelta(hours=24)
