"""Idempotent demo tariff, spots, and one driver."""

import os
from datetime import datetime, time, timezone

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.accounts.models import Driver, Vehicle
from apps.parking.models import Spot
from apps.tariffs.models import Tariff

User = get_user_model()

DEMO_EMAIL = "demo@example.com"
DEMO_PLATE = "A000AA"
DEFAULT_DEMO_PASSWORD = "ParkDemo-2026"
_TARIFF_FROM = datetime(2020, 1, 1, tzinfo=timezone.utc)


class Command(BaseCommand):
    help = "Create the demo tariff, spots P01..P12, and one driver. Safe to repeat."

    def handle(self, *args, **options):
        _tariff()
        for number in range(1, 13):
            Spot.objects.get_or_create(code=f"P{number:02d}")
        _driver()
        self.stdout.write("seed_demo: ready")


def _tariff():
    Tariff.objects.get_or_create(
        effective_from=_TARIFF_FROM,
        defaults={
            "timezone": "Asia/Bishkek",
            "day_starts_at": time(7, 0),
            "night_starts_at": time(23, 0),
            "day_rate_per_minute_kopecks": 200,
            "night_rate_per_minute_kopecks": 100,
        },
    )


def _driver():
    password = os.environ.get("DEMO_PASSWORD") or DEFAULT_DEMO_PASSWORD
    user = User.objects.filter(email=DEMO_EMAIL).first()
    if user is None:
        user = User.objects.create_user(email=DEMO_EMAIL, password=password)
    driver, _created = Driver.objects.get_or_create(user=user)
    Vehicle.objects.get_or_create(plate=DEMO_PLATE, defaults={"driver": driver})
