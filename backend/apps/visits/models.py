"""A stay on a spot, and the invoice total for that stay.

`amount_kopecks` is an integer number of minor currency units. It stays empty
until a later step calculates the bill. An active visit has no `exited_at`.
"""

from django.db import models
from django.db.models import F, Q

from apps.bookings.models import Booking
from apps.parking.models import Spot


class Visit(models.Model):
    spot = models.ForeignKey(Spot, on_delete=models.PROTECT, related_name="visits")
    booking = models.ForeignKey(
        Booking,
        on_delete=models.PROTECT,
        related_name="visits",
        null=True,
        blank=True,
    )
    plate = models.CharField(max_length=32)
    entered_at = models.DateTimeField()
    exited_at = models.DateTimeField(null=True, blank=True)
    amount_kopecks = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(exited_at__isnull=True) | Q(exited_at__gt=F("entered_at")),
                name="visit_exit_after_entry",
            ),
            models.UniqueConstraint(
                fields=["plate"],
                condition=Q(exited_at__isnull=True),
                name="visit_one_active_per_plate",
            ),
        ]

    def __str__(self):
        return self.plate
