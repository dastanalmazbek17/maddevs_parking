"""Reminder emails and the periodic expiry task."""

import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.db import connection
from django.test import override_settings

from apps.accounts.models import Driver, Vehicle
from apps.bookings.models import Booking, BookingStatus
from apps.bookings.tasks import expire_overdue_bookings as expire_task
from apps.notifications.models import BookingReminder
from apps.notifications.services import send_due_reminders
from apps.parking.models import Spot
from config.celery import app as celery_app

User = get_user_model()
UTC = timezone.utc
LOCMAIL = override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")


def _driver(email):
    user = User.objects.create_user(email=email, password="secret-pass")
    return Driver.objects.create(user=user)


def _booking(*, plate, code, ends_at, status=BookingStatus.ACTIVE, email="driver@example.com"):
    driver = _driver(email)
    vehicle = Vehicle.objects.create(driver=driver, plate=plate)
    spot = Spot.objects.create(code=code)
    starts_at = ends_at - timedelta(hours=1)
    return Booking.objects.create(
        spot=spot,
        vehicle=vehicle,
        starts_at=starts_at,
        ends_at=ends_at,
        status=status,
    )


@LOCMAIL
@pytest.mark.django_db
def test_a_booking_in_the_window_gets_one_email():
    now = datetime(2026, 6, 1, 4, 0, tzinfo=UTC)
    booking = _booking(plate="A123BC", code="P01", ends_at=now + timedelta(minutes=10))
    mail.outbox.clear()

    assert send_due_reminders(now=now) == 1
    assert send_due_reminders(now=now) == 0
    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == ["driver@example.com"]
    assert message.subject == "Бронь скоро заканчивается"
    assert "P01" in message.body
    assert "A123BC" in message.body
    assert "01.06.2026 10:10" in message.body
    assert "Asia/Bishkek" in message.body
    booking.reminder.refresh_from_db()
    assert booking.reminder.sent_at == now


@LOCMAIL
@pytest.mark.django_db
def test_window_boundaries():
    now = datetime(2026, 6, 1, 4, 0, tzinfo=UTC)
    inside = _booking(
        plate="IN0001",
        code="IN",
        ends_at=now + timedelta(minutes=10),
        email="inside@example.com",
    )
    early = _booking(
        plate="EARLY1",
        code="ER",
        ends_at=now + timedelta(minutes=10, seconds=1),
        email="early@example.com",
    )
    ended = _booking(
        plate="ENDED1",
        code="EN",
        ends_at=now,
        email="ended@example.com",
    )
    mail.outbox.clear()

    assert send_due_reminders(now=now) == 1
    assert mail.outbox[0].to == ["inside@example.com"]
    assert BookingReminder.objects.filter(booking=inside, sent_at=now).exists()
    assert not BookingReminder.objects.filter(booking=early).exists()
    assert not BookingReminder.objects.filter(booking=ended).exists()


@LOCMAIL
@pytest.mark.django_db
def test_only_active_and_checked_in_bookings_are_reminded():
    now = datetime(2026, 6, 1, 4, 0, tzinfo=UTC)
    ends_at = now + timedelta(minutes=5)
    kept = {
        BookingStatus.CANCELLED: ("CANC01", "CA"),
        BookingStatus.EXPIRED: ("EXPR01", "EX"),
        BookingStatus.COMPLETED: ("DONE01", "DO"),
    }
    for status, (plate, code) in kept.items():
        _booking(
            plate=plate,
            code=code,
            ends_at=ends_at,
            status=status,
            email=f"{status}@example.com",
        )
    staying = _booking(
        plate="STAY01",
        code="ST",
        ends_at=ends_at,
        status=BookingStatus.CHECKED_IN,
        email="staying@example.com",
    )
    mail.outbox.clear()

    assert send_due_reminders(now=now) == 1
    assert mail.outbox[0].to == ["staying@example.com"]
    assert BookingReminder.objects.filter(booking=staying).exists()
    assert BookingReminder.objects.exclude(booking=staying).count() == 0


@LOCMAIL
@pytest.mark.django_db
def test_a_missed_window_is_not_sent_later():
    now = datetime(2026, 6, 1, 4, 0, tzinfo=UTC)
    booking = _booking(plate="LATE01", code="LT", ends_at=now - timedelta(minutes=1))
    mail.outbox.clear()

    assert send_due_reminders(now=now) == 0
    assert mail.outbox == []
    assert not BookingReminder.objects.filter(booking=booking).exists()


@LOCMAIL
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_parallel_sends_leave_one_email_per_booking():
    now = datetime(2026, 6, 1, 4, 0, tzinfo=UTC)
    first = _booking(plate="RACE01", code="R1", ends_at=now + timedelta(minutes=8), email="one@example.com")
    second = _booking(plate="RACE02", code="R2", ends_at=now + timedelta(minutes=9), email="two@example.com")
    mail.outbox.clear()
    barrier = threading.Barrier(8)
    failures = []

    def attempt():
        try:
            barrier.wait(timeout=5)
            send_due_reminders(now=now)
        except Exception as exc:
            failures.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=attempt) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert failures == []
    assert sorted(message.to[0] for message in mail.outbox) == ["one@example.com", "two@example.com"]
    assert BookingReminder.objects.get(booking=first).sent_at == now
    assert BookingReminder.objects.get(booking=second).sent_at == now


@LOCMAIL
@pytest.mark.django_db
def test_a_failed_delivery_is_not_retried_and_does_not_stop_the_rest():
    now = datetime(2026, 6, 1, 4, 0, tzinfo=UTC)
    first = _booking(plate="FAIL01", code="F1", ends_at=now + timedelta(minutes=4), email="fail@example.com")
    second = _booking(plate="OK0001", code="F2", ends_at=now + timedelta(minutes=4), email="ok@example.com")
    mail.outbox.clear()

    def flaky(subject, body, from_email, recipient_list, fail_silently=False):
        if recipient_list == ["fail@example.com"]:
            raise ConnectionError("smtp down")
        mail.outbox.append(type("Message", (), {"to": recipient_list, "subject": subject, "body": body})())
        return 1

    with patch("apps.notifications.services.send_mail", side_effect=flaky):
        assert send_due_reminders(now=now) == 1
        assert send_due_reminders(now=now) == 0

    first.reminder.refresh_from_db()
    second.reminder.refresh_from_db()
    assert first.reminder.sent_at == now
    assert second.reminder.sent_at == now
    assert [message.to for message in mail.outbox] == [["ok@example.com"]]


@pytest.mark.django_db
def test_expire_task_releases_overdue_bookings_and_is_idempotent(caplog):
    now_start = datetime(2026, 6, 1, 4, 0, tzinfo=UTC)
    overdue = _booking(plate="OLD001", code="O1", ends_at=now_start + timedelta(hours=2))
    overdue.starts_at = now_start - timedelta(minutes=16)
    overdue.save(update_fields=["starts_at"])
    staying = _booking(
        plate="KEEP01",
        code="O2",
        ends_at=now_start + timedelta(hours=2),
        status=BookingStatus.CHECKED_IN,
        email="keep@example.com",
    )
    staying.starts_at = now_start - timedelta(minutes=16)
    staying.save(update_fields=["starts_at"])

    with caplog.at_level("INFO"):
        assert expire_task() == 1
    overdue.refresh_from_db()
    staying.refresh_from_db()
    assert overdue.status == BookingStatus.EXPIRED
    assert staying.status == BookingStatus.CHECKED_IN
    assert "Expired 1 overdue bookings" in caplog.text
    assert expire_task() == 0


def test_both_jobs_run_every_minute():
    schedule = celery_app.conf.beat_schedule
    expected = {
        "expire-overdue-bookings": "apps.bookings.tasks.expire_overdue_bookings",
        "send-due-reminders": "apps.notifications.tasks.send_due_reminders",
    }
    for name, task in expected.items():
        entry = schedule[name]
        assert entry["task"] == task
        assert entry["schedule"] == 60.0
