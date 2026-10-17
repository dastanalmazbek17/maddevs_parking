"""Booking services: interval rules, ownership, conflicts, expiry."""

import threading
from datetime import datetime, timedelta, timezone

import pytest
from django.contrib.auth import get_user_model
from django.db import connection

from apps.accounts.models import Driver, Vehicle
from apps.bookings.models import Booking, BookingStatus
from apps.bookings.services import cancel_booking, create_booking
from apps.parking.exceptions import (
    BookingConflict,
    BookingNotCancellable,
    BookingNotOwned,
    InvalidInterval,
    SpotNotFound,
    StartsInThePast,
    VehicleNotOwned,
)
from apps.parking.models import Spot

User = get_user_model()
UTC = timezone.utc


def _driver(email):
    user = User.objects.create_user(email=email, password="secret")
    return Driver.objects.create(user=user)


def _world():
    driver = _driver("driver@example.com")
    other = _driver("other@example.com")
    return {
        "driver": driver,
        "other": other,
        "vehicle": Vehicle.objects.create(driver=driver, plate="A123BC"),
        "other_vehicle": Vehicle.objects.create(driver=other, plate="B456DE"),
        "second_vehicle": Vehicle.objects.create(driver=driver, plate="C789FG"),
        "spot": Spot.objects.create(code="A"),
        "other_spot": Spot.objects.create(code="B"),
        "now": datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
    }


def _book(world, **overrides):
    values = dict(
        driver=world["driver"],
        vehicle=world["vehicle"],
        spot=world["spot"],
        starts_at=world["now"],
        ends_at=world["now"] + timedelta(hours=1),
        now=world["now"],
    )
    values.update(overrides)
    return create_booking(**values)


@pytest.mark.django_db
def test_duration_boundaries_and_touching_intervals():
    world = _world()
    now = world["now"]

    with pytest.raises(InvalidInterval) as too_short:
        _book(world, ends_at=now + timedelta(minutes=14, seconds=59))
    assert too_short.value.code == "invalid_interval"

    short_ok = _book(
        world,
        spot=world["other_spot"],
        vehicle=world["second_vehicle"],
        ends_at=now + timedelta(minutes=15),
    )
    assert short_ok.status == BookingStatus.ACTIVE

    day = _book(
        world,
        starts_at=now + timedelta(days=2),
        ends_at=now + timedelta(days=3),
        vehicle=world["second_vehicle"],
    )
    assert day.ends_at - day.starts_at == timedelta(hours=24)

    with pytest.raises(InvalidInterval):
        _book(
            world,
            starts_at=now + timedelta(days=5),
            ends_at=now + timedelta(days=6, seconds=1),
        )
    with pytest.raises(InvalidInterval):
        _book(world, ends_at=now)
    with pytest.raises(InvalidInterval):
        create_booking(
            world["driver"],
            world["vehicle"],
            world["spot"],
            datetime(2026, 6, 1, 12, 0),
            datetime(2026, 6, 1, 13, 0),
            now=now,
        )

    touching = _book(
        world,
        starts_at=short_ok.ends_at,
        ends_at=short_ok.ends_at + timedelta(minutes=15),
        spot=world["other_spot"],
        vehicle=world["vehicle"],
    )
    assert touching.pk != short_ok.pk


@pytest.mark.django_db
def test_start_grace_and_ownership():
    world = _world()
    now = world["now"]
    allowed = _book(world, starts_at=now - timedelta(minutes=1), ends_at=now + timedelta(hours=1))
    assert allowed.status == BookingStatus.ACTIVE

    with pytest.raises(StartsInThePast) as late:
        _book(
            world,
            starts_at=now - timedelta(minutes=1, microseconds=1),
            ends_at=now + timedelta(hours=1),
            spot=world["other_spot"],
            vehicle=world["second_vehicle"],
        )
    assert late.value.code == "starts_in_the_past"

    with pytest.raises(VehicleNotOwned) as foreign:
        _book(world, vehicle=world["other_vehicle"])
    assert foreign.value.code == "vehicle_not_owned"
    with pytest.raises(SpotNotFound):
        _book(world, spot=Spot(code="missing"))
    assert Booking.objects.count() == 1


@pytest.mark.django_db
def test_overlapping_spot_or_vehicle_is_a_conflict_and_released_statuses_are_not():
    world = _world()
    now = world["now"]
    first = _book(world)

    with pytest.raises(BookingConflict) as spot_conflict:
        _book(
            world,
            vehicle=world["second_vehicle"],
            starts_at=now + timedelta(minutes=30),
            ends_at=now + timedelta(hours=2),
        )
    assert spot_conflict.value.code == "booking_conflict"

    with pytest.raises(BookingConflict):
        _book(
            world,
            spot=world["other_spot"],
            starts_at=now + timedelta(minutes=30),
            ends_at=now + timedelta(hours=2),
        )
    assert Booking.objects.count() == 1

    cancel_booking(world["driver"], first, now=now)
    replacement = _book(world)
    assert replacement.pk != first.pk

    replacement.status = BookingStatus.EXPIRED
    replacement.save(update_fields=["status"])
    replacement.refresh_from_db()
    assert replacement.status == BookingStatus.EXPIRED
    after_expiry = _book(
        world,
        starts_at=now + timedelta(minutes=15),
        ends_at=now + timedelta(hours=2),
        now=now + timedelta(minutes=15),
    )
    assert after_expiry.status == BookingStatus.ACTIVE


@pytest.mark.django_db
def test_cancel_is_idempotent_and_rejects_the_wrong_driver_or_status():
    world = _world()
    booking = _book(world)
    with pytest.raises(BookingNotOwned) as foreign:
        cancel_booking(world["other"], booking, now=world["now"])
    assert foreign.value.code == "booking_not_owned"
    booking.refresh_from_db()
    assert booking.status == BookingStatus.ACTIVE

    cancelled = cancel_booking(world["driver"], booking, now=world["now"])
    again = cancel_booking(world["driver"], cancelled, now=world["now"])
    assert again.status == BookingStatus.CANCELLED
    assert Booking.objects.filter(status=BookingStatus.CANCELLED).count() == 1

    active = _book(
        world,
        starts_at=world["now"] + timedelta(hours=3),
        ends_at=world["now"] + timedelta(hours=4),
    )
    active.status = BookingStatus.CHECKED_IN
    active.save(update_fields=["status"])
    with pytest.raises(BookingNotCancellable) as denied:
        cancel_booking(world["driver"], active, now=world["now"])
    assert denied.value.code == "booking_not_cancellable"
    active.status = BookingStatus.COMPLETED
    active.save(update_fields=["status"])
    with pytest.raises(BookingNotCancellable):
        cancel_booking(world["driver"], active, now=world["now"])
    active.status = BookingStatus.EXPIRED
    active.save(update_fields=["status"])
    with pytest.raises(BookingNotCancellable):
        cancel_booking(world["driver"], active, now=world["now"])


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_parallel_bookings_of_one_spot_allow_a_single_winner():
    driver = _driver("racer@example.com")
    vehicle = Vehicle.objects.create(driver=driver, plate="RACE01")
    spot = Spot.objects.create(code="R1")
    now = datetime(2026, 6, 2, 9, 0, tzinfo=UTC)
    starts_at = now
    ends_at = now + timedelta(hours=1)
    barrier = threading.Barrier(8)
    winners = []
    conflicts = []
    failures = []
    lock = threading.Lock()

    def attempt():
        try:
            barrier.wait(timeout=5)
            booking = create_booking(
                driver, vehicle, spot, starts_at, ends_at, now=now
            )
            with lock:
                winners.append(booking.pk)
        except BookingConflict:
            with lock:
                conflicts.append(True)
        except Exception as exc:
            with lock:
                failures.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=attempt) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert failures == []
    assert len(winners) == 1
    assert len(conflicts) == 7
    assert list(Booking.objects.filter(status=BookingStatus.ACTIVE).values_list("pk", flat=True)) == winners
