"""Spot reservations.

Bookings that still hold a spot cannot overlap. The rule is a PostgreSQL
exclusion constraint, so two concurrent inserts cannot both succeed.
"""

from datetime import timedelta

from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeBoundary, RangeOperators
from django.db import models
from django.db.models import F, Func, Q

from apps.parking.models import Spot


class TsTzRange(Func):
    """Build a half-open `[start, end)` timestamptz range in SQL."""

    function = "TSTZRANGE"
    output_field = DateTimeRangeField()


class BookingStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    CHECKED_IN = "checked_in", "Checked in"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"
    EXPIRED = "expired", "Expired"


# Statuses that still occupy the spot for other bookings.
HOLDING_SPOT_STATUSES = (BookingStatus.ACTIVE, BookingStatus.CHECKED_IN)


class Booking(models.Model):
    spot = models.ForeignKey(Spot, on_delete=models.PROTECT, related_name="bookings")
    vehicle = models.ForeignKey(
        "accounts.Vehicle",
        on_delete=models.PROTECT,
        related_name="bookings",
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    status = models.CharField(
        max_length=16,
        choices=BookingStatus.choices,
        default=BookingStatus.ACTIVE,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=F("starts_at")),
                name="booking_ends_after_start",
            ),
            models.CheckConstraint(
                condition=Q(ends_at__gte=F("starts_at") + timedelta(minutes=15))
                & Q(ends_at__lte=F("starts_at") + timedelta(hours=24)),
                name="booking_duration_15m_to_24h",
            ),
            models.CheckConstraint(
                condition=Q(status__in=BookingStatus.values),
                name="booking_status_known",
            ),
            ExclusionConstraint(
                name="booking_no_overlap_per_spot",
                expressions=[
                    ("spot", RangeOperators.EQUAL),
                    (
                        TsTzRange(F("starts_at"), F("ends_at"), RangeBoundary()),
                        RangeOperators.OVERLAPS,
                    ),
                ],
                condition=Q(status__in=HOLDING_SPOT_STATUSES),
            ),
            ExclusionConstraint(
                name="booking_no_overlap_per_vehicle",
                expressions=[
                    ("vehicle", RangeOperators.EQUAL),
                    (
                        TsTzRange(F("starts_at"), F("ends_at"), RangeBoundary()),
                        RangeOperators.OVERLAPS,
                    ),
                ],
                condition=Q(status__in=HOLDING_SPOT_STATUSES),
            ),
        ]

    def __str__(self):
        return f"booking {self.pk} @ {self.spot_id}"
