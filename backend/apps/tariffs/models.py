"""A dated day/night price list.

Instants are UTC. `day_starts_at` and `night_starts_at` are clock times in
`timezone`. Rates are integer kopecks per minute. The initial row is seeded
by a migration: Asia/Bishkek, day 07:00–23:00 at 200, night 23:00–07:00 at 100.
"""

from django.db import models
from django.db.models import F, Q


class Tariff(models.Model):
    effective_from = models.DateTimeField(unique=True)
    timezone = models.CharField(max_length=64)
    day_starts_at = models.TimeField()
    night_starts_at = models.TimeField()
    day_rate_per_minute_kopecks = models.PositiveIntegerField()
    night_rate_per_minute_kopecks = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=~Q(day_starts_at=F("night_starts_at")),
                name="tariff_day_and_night_boundaries_differ",
            ),
        ]

    def __str__(self):
        return f"tariff from {self.effective_from.isoformat()}"
