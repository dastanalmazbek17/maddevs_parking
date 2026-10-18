"""Spot socket: a public signal, sent only after the database commits."""

import json
import threading
from datetime import datetime, timedelta, timezone

import pytest
from asgiref.sync import async_to_sync, sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.db import connection, transaction

from apps.accounts.models import Driver, Vehicle
from apps.bookings.models import Booking
from apps.bookings.services import cancel_booking, create_booking, expire_overdue_bookings
from apps.parking.models import Spot
from apps.parking.tasks import notify_spots_changed as notify_task
from apps.visits.services import enter, exit_visit
from config.asgi import application
from config.celery import app as celery_app

User = get_user_model()
UTC = timezone.utc
SIGNAL = {"type": "spots.changed"}


def _run(scenario):
    async_to_sync(scenario)()


async def _open(origin=None):
    headers = []
    if origin is not None:
        headers.append((b"origin", origin.encode("latin1")))
    communicator = WebsocketCommunicator(application, "/ws/spots/", headers=headers)
    connected, _close_code = await communicator.connect()
    return communicator, connected


def _driver(email):
    user = User.objects.create_user(email=email, password="secret-pass")
    return Driver.objects.create(user=user)


def _book(email, plate, code, when):
    driver = _driver(email)
    vehicle = Vehicle.objects.create(driver=driver, plate=plate)
    spot = Spot.objects.create(code=code)
    return create_booking(driver, vehicle, spot, when, when + timedelta(hours=1), now=when), driver


@pytest.mark.django_db
def test_socket_accepts_a_public_client_and_rejects_a_foreign_origin():
    async def scenario():
        allowed, connected = await _open("http://localhost")
        assert connected
        await allowed.disconnect()
        denied, connected = await _open("http://evil.example")
        assert not connected
        await denied.disconnect()

    _run(scenario)


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_booking_cancel_entry_and_exit_each_signal(django_capture_on_commit_callbacks):
    when = datetime(2026, 6, 1, 4, 0, tzinfo=UTC)

    async def scenario():
        client, connected = await _open("http://localhost")
        assert connected

        def book():
            with django_capture_on_commit_callbacks(execute=True):
                return _book("ws@example.com", "WS001AA", "W1", when)

        booking, driver = await sync_to_async(book)()
        assert json.loads(await client.receive_from(timeout=2)) == SIGNAL

        def cancel():
            with django_capture_on_commit_callbacks(execute=True):
                cancel_booking(driver, booking, now=when)

        await sync_to_async(cancel)()
        assert json.loads(await client.receive_from(timeout=2)) == SIGNAL

        def drive_in():
            with django_capture_on_commit_callbacks(execute=True):
                Spot.objects.create(code="W2")
                enter("WALK01", now=when)

        await sync_to_async(drive_in)()
        assert json.loads(await client.receive_from(timeout=2)) == SIGNAL

        def drive_out():
            with django_capture_on_commit_callbacks(execute=True):
                exit_visit("WALK01", now=when + timedelta(minutes=30))

        await sync_to_async(drive_out)()
        assert json.loads(await client.receive_from(timeout=2)) == SIGNAL
        await client.disconnect()

    _run(scenario)


@pytest.mark.django_db
def test_a_rolled_back_booking_sends_nothing(django_capture_on_commit_callbacks):
    when = datetime(2026, 6, 1, 4, 0, tzinfo=UTC)

    async def scenario():
        client, connected = await _open("http://localhost")
        assert connected

        def rollback():
            with django_capture_on_commit_callbacks(execute=True):
                with pytest.raises(RuntimeError):
                    with transaction.atomic():
                        _book("rb@example.com", "RB001AA", "RB", when)
                        raise RuntimeError("rollback")

        await sync_to_async(rollback)()
        assert await client.receive_nothing(timeout=0.2)
        await client.disconnect()

    _run(scenario)


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_expiry_signals_only_when_a_booking_was_released(django_capture_on_commit_callbacks):
    when = datetime(2026, 6, 1, 8, 0, tzinfo=UTC)

    async def scenario():
        client, connected = await _open("http://localhost")
        assert connected

        def quiet():
            with django_capture_on_commit_callbacks(execute=True):
                return expire_overdue_bookings(now=when)

        assert await sync_to_async(quiet)() == 0
        assert await client.receive_nothing(timeout=0.2)

        def prepare():
            with django_capture_on_commit_callbacks(execute=True):
                booking, _owner = _book("ex@example.com", "EX001AA", "EX", when)
            booking.starts_at = when - timedelta(minutes=20)
            booking.save(update_fields=["starts_at"])

        await sync_to_async(prepare)()
        assert json.loads(await client.receive_from(timeout=2)) == SIGNAL

        def overdue():
            with django_capture_on_commit_callbacks(execute=True):
                return expire_overdue_bookings(now=when + timedelta(minutes=20))

        assert await sync_to_async(overdue)() == 1
        assert json.loads(await client.receive_from(timeout=2)) == SIGNAL
        await client.disconnect()

    _run(scenario)


@pytest.mark.django_db
def test_periodic_notify_sends_and_is_scheduled_every_fifteen_seconds(django_capture_on_commit_callbacks):
    async def scenario():
        client, connected = await _open("http://localhost")
        assert connected

        def tick():
            with django_capture_on_commit_callbacks(execute=True):
                notify_task()

        await sync_to_async(tick)()
        assert json.loads(await client.receive_from(timeout=2)) == SIGNAL
        await client.disconnect()

    _run(scenario)
    entry = celery_app.conf.beat_schedule["notify-spots-changed"]
    assert entry["task"] == "apps.parking.tasks.notify_spots_changed"
    assert entry["schedule"] == 15.0


@pytest.mark.django_db
def test_two_clients_both_receive_the_signal(django_capture_on_commit_callbacks):
    when = datetime(2026, 6, 1, 4, 0, tzinfo=UTC)

    async def scenario():
        first, connected = await _open("http://localhost")
        second, also = await _open("http://127.0.0.1")
        assert connected and also

        def book():
            with django_capture_on_commit_callbacks(execute=True):
                _book("two@example.com", "TWO01AA", "T1", when)

        await sync_to_async(book)()
        assert json.loads(await first.receive_from(timeout=2)) == SIGNAL
        assert json.loads(await second.receive_from(timeout=2)) == SIGNAL
        await first.disconnect()
        await second.disconnect()

    _run(scenario)


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_the_signal_is_not_sent_before_other_connections_see_the_row():
    when = datetime(2026, 6, 1, 4, 0, tzinfo=UTC)

    async def scenario():
        client, connected = await _open("http://localhost")
        assert connected
        started = threading.Event()
        release = threading.Event()
        box = {}

        def hold_open():
            try:
                with transaction.atomic():
                    booking, _owner = _book("late@example.com", "LATE1AA", "L1", when)
                    box["pk"] = booking.pk
                    started.set()
                    assert release.wait(timeout=5)
            finally:
                connection.close()

        worker = threading.Thread(target=hold_open)
        worker.start()
        assert await sync_to_async(started.wait)(5)

        def visible():
            try:
                return Booking.objects.filter(pk=box["pk"]).exists()
            finally:
                connection.close()

        assert not await sync_to_async(visible, thread_sensitive=False)()
        assert await client.receive_nothing(timeout=0.2)
        release.set()
        await sync_to_async(worker.join)(5)
        assert not worker.is_alive()
        assert await sync_to_async(visible, thread_sensitive=False)()
        assert json.loads(await client.receive_from(timeout=2)) == SIGNAL
        await client.disconnect()

    _run(scenario)
