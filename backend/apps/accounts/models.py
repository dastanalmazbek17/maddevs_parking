"""Driver profile linked to a Django user, and the plates registered to that driver."""

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.accounts.plates import PlateField


class Driver(models.Model):
    """Profile for a Django user. The login email and password live on the user."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="driver",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.email


class Vehicle(models.Model):
    """One normalized plate. The same plate cannot belong to two drivers."""

    driver = models.ForeignKey(
        Driver,
        on_delete=models.CASCADE,
        related_name="vehicles",
    )
    plate = PlateField(max_length=32, unique=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=~Q(plate=""),
                name="vehicle_plate_not_blank",
            ),
        ]

    def __str__(self):
        return self.plate
