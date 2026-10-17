"""Entry, exit, and their races with expiry."""

import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.accounts.models import Driver, Vehicle
from apps.bookings.models import BookingStatus
from apps.bookings.services import create_booking, expire_overdue_bookings
from apps.parking.exceptions import (
    DoubleEntry,
    ExitNotAfterEntry,
    InvalidPlate,
    NoActiveVisit,
    NoFreePlace,
)
from apps.parking.models import Spot
from apps.tariffs.models import Tariff
from apps.visits.models import Invoice, Visit
from apps.visits.services import enter, exit_visit

User = get_user_model()
BISHKEK = ZoneInfo("Asia/Bishkek")


def _driver(email):
    user = User.objects.create_user(email=email, password="secret")
    return Driver.objects.create(user=user)


def _at(hour, minute=0, second=0, microsecond=0):
    return datetime(2026, 6, 1, hour, minute, second, microsecond, tzinfo=BISHKEK)


@pytest.fixture
def yard():
    driver = _driver("driver@example.com")
    other = _driver("other@example.com")
    spots = [Spot.objects.create(code=code) for code in ("B", "A", "C")]
    vehicle = Vehicle.objects.create(driver=driver, plate="A123BC")
    return {
        "driver": driver,
        "other": other,
        "spots": spots,
        "vehicle": vehicle,
        "other_vehicle": Vehicle.objects.create(driver=other, plate="B456DE"),
    }


def _reserve(yard, spot, start, vehicle=None):
    return create_booking(
        yard["driver"] if vehicle is None else vehicle.driver,
        vehicle or yard["vehicle"],
        spot,
        start,
        start + timedelta(minutes=15),
        now=start,
    )


@pytest.mark.django_db
def test_entry_window_boundaries(yard):
    spot = yard["spots"][0]
    start = _at(10)
    booking = _reserve(yard, spot, start)

    at_start = enter("A123BC", now=start)
    assert at_start.spot_id == spot.pk
    assert at_start.booking_id == booking.pk
    assert at_start.driver_id == yard["driver"].pk
    booking.refresh_from_db()
    assert booking.status == BookingStatus.CHECKED_IN

    Visit.objects.all().delete()
    booking.status = BookingStatus.ACTIVE
    booking.save(update_fields=["status"])
    last_moment = enter("A123BC", now=start + timedelta(minutes=15) - timedelta(microseconds=1))
    assert last_moment.booking_id == booking.pk
    booking.refresh_from_db()
    assert booking.status == BookingStatus.CHECKED_IN


@pytest.mark.django_db
def test_exact_end_of_the_window_is_a_walk_in(yard):
    spot = yard["spots"][0]
    start = _at(10)
    booking = _reserve(yard, spot, start)
    visit = enter("A123BC", now=start + timedelta(minutes=15))

    assert visit.booking_id is None
    assert visit.spot_id == spot.pk
    assert visit.driver_id == yard["driver"].pk
    booking.refresh_from_db()
    assert booking.status == BookingStatus.ACTIVE


@pytest.mark.django_db
def test_early_arrival_does_not_take_the_held_spot_or_the_booking(yard):
    held = yard["spots"][0]
    other = yard["spots"][1]
    start = _at(10)
    booking = _reserve(yard, held, start)
    visit = enter("A123BC", now=start - timedelta(minutes=10))

    assert visit.booking_id is None
    assert visit.spot_id == other.pk
    assert visit.driver_id == yard["driver"].pk
    booking.refresh_from_db()
    assert booking.status == BookingStatus.ACTIVE
    assert booking.spot_id == held.pk


@pytest.mark.django_db
def test_taken_booking_spot_assigns_another_and_keeps_the_original(yard):
    booked = yard["spots"][0]
    replacement = yard["spots"][1]
    left_alone = yard["spots"][2]
    start = _at(10)
    booking = _reserve(yard, booked, start)
    blocker = enter(yard["other_vehicle"].plate, now=start - timedelta(hours=2))
    assert blocker.spot_id == booked.pk

    visit = enter("a 123 bc", now=start)
    assert visit.plate == "A123BC"
    assert visit.spot_id == replacement.pk
    assert visit.booking_id == booking.pk
    booking.refresh_from_db()
    assert booking.status == BookingStatus.CHECKED_IN
    assert booking.spot_id == booked.pk

    exit_visit(yard["other_vehicle"].plate, now=start + timedelta(minutes=1))
    third = enter("C789FG", now=start + timedelta(minutes=1))
    assert third.spot_id == left_alone.pk
    assert third.booking_id is None

    after_end = enter("D111HH", now=booking.ends_at)
    assert after_end.spot_id == booked.pk


@pytest.mark.django_db
def test_no_free_place_leaves_the_booking_active(yard):
    spot = yard["spots"][0]
    Spot.objects.exclude(pk=spot.pk).delete()
    start = _at(10)
    booking = _reserve(yard, spot, start)
    enter(yard["other_vehicle"].plate, now=start - timedelta(hours=2))

    with pytest.raises(NoFreePlace) as denied:
        enter("A123BC", now=start)
    assert denied.value.code == "no_free_place"
    booking.refresh_from_db()
    assert booking.status == BookingStatus.ACTIVE
    assert Visit.objects.filter(plate="A123BC").count() == 0


@pytest.mark.django_db
def test_double_entry_unknown_plate_and_plate_spellings(yard):
    enter("A123BC", now=_at(8))
    with pytest.raises(DoubleEntry) as again:
        enter("А123ВС", now=_at(8, 5))
    assert again.value.code == "double_entry"
    assert Visit.objects.filter(exited_at__isnull=True).count() == 1

    unknown = enter("ZZ999ZZ", now=_at(8))
    assert unknown.driver_id is None
    assert unknown.booking_id is None
    with pytest.raises(InvalidPlate):
        enter("", now=_at(8))


@pytest.mark.django_db
def test_exit_bills_the_stay_and_completes_the_booking(yard):
    start = _at(10)
    booking = _reserve(yard, yard["spots"][0], start)
    enter("A123BC", now=start)
    visit, invoice = exit_visit("A123BC", now=start + timedelta(minutes=30))

    assert invoice.amount_kopecks == 6000
    assert invoice.issued_at == start + timedelta(minutes=30)
    assert type(invoice.amount_kopecks) is int
    visit.refresh_from_db()
    assert visit.exited_at == start + timedelta(minutes=30)
    booking.refresh_from_db()
    assert booking.status == BookingStatus.COMPLETED

    with pytest.raises(NoActiveVisit) as repeat:
        exit_visit("A123BC", now=start + timedelta(minutes=40))
    assert repeat.value.code == "no_active_visit"
    assert Invoice.objects.count() == 1


@pytest.mark.django_db
def test_exit_without_entry_creates_nothing(yard):
    with pytest.raises(NoActiveVisit):
        exit_visit("A123BC", now=_at(11))
    assert Visit.objects.count() == 0
    assert Invoice.objects.count() == 0


@pytest.mark.django_db
def test_exit_at_or_before_entry_is_rejected(yard):
    entered = _at(10)
    enter("A123BC", now=entered)
    with pytest.raises(ExitNotAfterEntry) as same:
        exit_visit("A123BC", now=entered)
    assert same.value.code == "exit_not_after_entry"
    with pytest.raises(ExitNotAfterEntry):
        exit_visit("A123BC", now=entered - timedelta(seconds=1))
    assert Visit.objects.get().exited_at is None
    assert Invoice.objects.count() == 0


@pytest.mark.django_db
def test_failed_pricing_keeps_the_visit_open(yard):
    entered = _at(10)
    enter("A123BC", now=entered)
    Tariff.objects.all().delete()
    with pytest.raises(ValueError):
        exit_visit("A123BC", now=entered + timedelta(minutes=30))
    assert Visit.objects.get().exited_at is None
    assert Invoice.objects.count() == 0


@pytest.mark.django_db
def test_check_in_locks_the_booking_and_walk_in_locks_one_spot(yard):
    start = _at(10)
    _reserve(yard, yard["spots"][0], start)
    with CaptureQueriesContext(connection) as booked:
        enter("A123BC", now=start)
    booking_locks = [
        query["sql"]
        for query in booked.captured_queries
        if "FOR UPDATE" in query["sql"] and "bookings_booking" in query["sql"]
    ]
    assert booking_locks

    with CaptureQueriesContext(connection) as walked:
        enter("ZZ999ZZ", now=_at(8))
    spot_locks = [
        query["sql"]
        for query in walked.captured_queries
        if "SKIP LOCKED" in query["sql"] and "parking_spot" in query["sql"]
    ]
    assert len(spot_locks) == 1
    assert "LIMIT 1" in spot_locks[0]


@pytest.mark.django_db
def test_walk_in_picks_the_lowest_spot_pk(yard):
    visit = enter("ZZ999ZZ", now=_at(8))
    assert visit.spot_id == yard["spots"][0].pk


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_parallel_entries_of_one_plate_leave_one_visit():
    driver = _driver("one-plate@example.com")
    Vehicle.objects.create(driver=driver, plate="SAME01")
    for index in range(8):
        Spot.objects.create(code=f"S{index}")
    now = _at(9)
    barrier = threading.Barrier(8)
    wins = []
    denied = []
    failures = []
    lock = threading.Lock()

    def attempt():
        try:
            barrier.wait(timeout=5)
            visit = enter("SAME01", now=now)
            with lock:
                wins.append(visit.pk)
        except DoubleEntry:
            with lock:
                denied.append(True)
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
    assert len(wins) == 1
    assert len(denied) == 7
    assert Visit.objects.filter(exited_at__isnull=True).count() == 1


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_parallel_walk_ins_fill_distinct_spots():
    for index in range(3):
        Spot.objects.create(code=f"K{index}")
    now = _at(9)
    plates = [f"P{index:03d}AA" for index in range(6)]
    barrier = threading.Barrier(len(plates))
    wins = []
    full = []
    failures = []
    lock = threading.Lock()

    def attempt(plate):
        try:
            barrier.wait(timeout=5)
            visit = enter(plate, now=now)
            with lock:
                wins.append(visit.spot_id)
        except NoFreePlace:
            with lock:
                full.append(plate)
        except Exception as exc:
            with lock:
                failures.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=attempt, args=(plate,)) for plate in plates]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert failures == []
    assert len(wins) == 3
    assert len(set(wins)) == 3
    assert len(full) == 3
    assert Visit.objects.filter(exited_at__isnull=True).count() == 3


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_entry_and_expiry_never_leave_a_visit_on_an_expired_booking():
    for index in range(12):
        driver = _driver(f"race{index}@example.com")
        vehicle = Vehicle.objects.create(driver=driver, plate=f"E{index:03d}AA")
        spot = Spot.objects.create(code=f"E{index}")
        start = _at(10)
        booking = create_booking(
            driver,
            vehicle,
            spot,
            start,
            start + timedelta(hours=1),
            now=start,
        )
        barrier = threading.Barrier(2)
        errors = []

        def check_in():
            try:
                barrier.wait(timeout=5)
                enter(vehicle.plate, now=start + timedelta(minutes=14))
            except Exception as exc:
                errors.append(exc)
            finally:
                connection.close()

        def expire():
            try:
                barrier.wait(timeout=5)
                expire_overdue_bookings(now=start + timedelta(minutes=15))
            except Exception as exc:
                errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=check_in), threading.Thread(target=expire)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert errors == []
        booking.refresh_from_db()
        linked = Visit.objects.filter(booking=booking)
        if linked.exists():
            assert booking.status == BookingStatus.CHECKED_IN
            assert linked.count() == 1
        else:
            assert booking.status == BookingStatus.EXPIRED
        Visit.objects.all().delete()
        booking.delete()
        vehicle.delete()
        spot.delete()
        driver.user.delete()
