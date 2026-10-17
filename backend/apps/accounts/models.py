"""Driver profile: email and the plates registered to that driver."""

from django.db import models
from django.db.models import Q

from apps.accounts.plates import PlateField


class Driver(models.Model):
    """A driver. Sign-in is not modeled here."""

    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email


class Vehicle(models.Model):
    """A plate listed on a driver's profile. Stored text is normalized."""

    driver = models.ForeignKey(
        Driver,
        on_delete=models.CASCADE,
        related_name="vehicles",
    )
    plate = PlateField(max_length=32)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["driver", "plate"],
                name="vehicle_plate_per_driver",
            ),
            models.CheckConstraint(
                condition=~Q(plate=""),
                name="vehicle_plate_not_blank",
            ),
        ]

    def __str__(self):
        return self.plate
