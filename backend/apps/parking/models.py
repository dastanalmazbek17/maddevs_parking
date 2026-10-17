"""Parking spots. Occupancy is derived from bookings and visits, not stored.

A spot is reserved when an active booking covers the current instant and that
booking has no visit yet. That rule is not a column.
"""

from django.db import models


class Spot(models.Model):
    code = models.CharField(max_length=16, unique=True)

    def __str__(self):
        return self.code
