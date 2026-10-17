"""Parking spots. Occupancy is derived from bookings and visits, not stored."""

from django.db import models


class Spot(models.Model):
    code = models.CharField(max_length=16, unique=True)

    def __str__(self):
        return self.code
