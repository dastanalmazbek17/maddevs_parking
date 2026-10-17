"""Spot reservations.

Active bookings of one spot cannot overlap. The rule is a PostgreSQL exclusion
constraint, so two concurrent inserts cannot both succeed.
"""

from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeBoundary, RangeOperators
from django.db import models
from django.db.models import F, Func, Q

from apps.accounts.models import Driver
from apps.accounts.plates import PlateField
from apps.parking.models import Spot


class TsTzRange(Func):
    """Build a half-open `[start, end)` timestamptz range in SQL."""

    function = "TSTZRANGE"
    output_field = DateTimeRangeField()


class BookingStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    CANCELLED = "cancelled", "Cancelled"
    EXPIRED = "expired", "Expired"
    COMPLETED = "completed", "Completed"


class Booking(models.Model):
    spot = models.ForeignKey(Spot, on_delete=models.PROTECT, related_name="bookings")
    driver = models.ForeignKey(Driver, on_delete=models.PROTECT, related_name="bookings")
    plate = PlateField(max_length=32)
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
                condition=Q(status__in=BookingStatus.values),
                name="booking_status_known",
            ),
            models.CheckConstraint(
                condition=~Q(plate=""),
                name="booking_plate_not_blank",
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
                condition=Q(status=BookingStatus.ACTIVE),
            ),
        ]

    def __str__(self):
        return f"{self.plate} @ {self.spot_id}"
