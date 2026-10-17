"""A stay on a spot, and the invoice issued for that stay.

An active visit has no `exited_at`. At most one active visit may occupy a spot,
and at most one active visit may use a plate. The bill is an `Invoice` row,
not columns on the visit. `amount_kopecks` is an integer number of minor units.
"""

from django.db import models
from django.db.models import F, Q

from apps.accounts.plates import PlateField
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
    plate = PlateField(max_length=32)
    entered_at = models.DateTimeField()
    exited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(exited_at__isnull=True) | Q(exited_at__gt=F("entered_at")),
                name="visit_exit_after_entry",
            ),
            models.CheckConstraint(
                condition=~Q(plate=""),
                name="visit_plate_not_blank",
            ),
            models.UniqueConstraint(
                fields=["plate"],
                condition=Q(exited_at__isnull=True),
                name="visit_one_active_per_plate",
            ),
            models.UniqueConstraint(
                fields=["spot"],
                condition=Q(exited_at__isnull=True),
                name="visit_one_active_per_spot",
            ),
        ]

    def __str__(self):
        return self.plate


class Invoice(models.Model):
    """The bill for one visit. A visit has at most one invoice."""

    visit = models.OneToOneField(Visit, on_delete=models.PROTECT, related_name="invoice")
    amount_kopecks = models.PositiveIntegerField()
    issued_at = models.DateTimeField()

    def __str__(self):
        return f"{self.amount_kopecks} kopecks for visit {self.visit_id}"
