"""Spot colour is derived, and it uses the same hold window as walk-in entry."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model

from apps.accounts.models import Driver, Vehicle
from apps.bookings.services import create_booking
from apps.parking.models import Spot
from apps.parking.services import BOOKED, FREE, OCCUPIED, spot_statuses
from apps.visits.services import enter

User = get_user_model()
BISHKEK = ZoneInfo("Asia/Bishkek")


def _at(hour, minute=0, second=0, microsecond=0):
    return datetime(2026, 6, 1, hour, minute, second, microsecond, tzinfo=BISHKEK)


@pytest.mark.django_db
def test_spot_statuses_follow_the_hold_window():
    driver_user = User.objects.create_user(email="map@example.com", password="secret")
    driver = Driver.objects.create(user=driver_user)
    vehicle = Vehicle.objects.create(driver=driver, plate="A123BC")
    first = Spot.objects.create(code="B")
    second = Spot.objects.create(code="A")
    start = _at(10)
    create_booking(
        driver,
        vehicle,
        first,
        start,
        start + timedelta(hours=2),
        now=start - timedelta(minutes=20),
    )

    def states(now):
        return {spot.pk: state for spot, state in spot_statuses(now=now)}

    assert states(start - timedelta(minutes=15, microseconds=1))[first.pk] == FREE
    assert states(start - timedelta(minutes=15))[first.pk] == BOOKED
    assert states(start - timedelta(minutes=10))[first.pk] == BOOKED
    assert states(start + timedelta(minutes=10))[first.pk] == BOOKED
    assert states(start + timedelta(minutes=15))[first.pk] == FREE
    assert states(start + timedelta(hours=2)) == {first.pk: FREE, second.pk: FREE}

    later = start + timedelta(hours=5)
    create_booking(
        driver,
        vehicle,
        second,
        later,
        later + timedelta(hours=1),
        now=start,
    )
    assert states(start)[second.pk] == FREE

    enter("ZZ999ZZ", now=start - timedelta(hours=2))
    assert states(start)[first.pk] == OCCUPIED
    assert [spot.pk for spot, _state in spot_statuses(now=start)] == [first.pk, second.pk]
