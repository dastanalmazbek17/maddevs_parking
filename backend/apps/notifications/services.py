"""One reminder email in the last 10 minutes of a booking."""

import logging
from datetime import timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction

from apps.bookings.models import Booking, BookingStatus
from apps.notifications.models import BookingReminder
from apps.parking.services import resolve_now
from apps.tariffs.models import Tariff

logger = logging.getLogger(__name__)

REMINDER_WINDOW = timedelta(minutes=10)
REMINDER_STATUSES = (BookingStatus.ACTIVE, BookingStatus.CHECKED_IN)


def send_due_reminders(*, now=None):
    """Send at most one reminder for each booking inside the last 10 minutes.

    The claim is committed before delivery. A failed send is not retried.
    Returns how many messages were handed to the mail backend.
    """

    now = resolve_now(now)
    sent = 0
    due = (
        Booking.objects.filter(
            status__in=REMINDER_STATUSES,
            ends_at__gt=now,
            ends_at__lte=now + REMINDER_WINDOW,
        )
        .select_related("spot", "vehicle__driver__user")
        .order_by("pk")
    )
    for booking in due:
        _ensure_reminder(booking.pk)
        if not _claim(booking.pk, now):
            continue
        try:
            send_mail(
                _subject(),
                _body(booking),
                settings.DEFAULT_FROM_EMAIL,
                [_recipient(booking)],
                fail_silently=False,
            )
        except Exception:
            logger.exception(
                "Reminder for booking %s was marked sent but delivery failed",
                booking.pk,
            )
            continue
        sent += 1
    return sent


def _ensure_reminder(booking_id):
    try:
        with transaction.atomic():
            BookingReminder.objects.create(booking_id=booking_id)
    except IntegrityError:
        return


def _claim(booking_id, now):
    with transaction.atomic():
        claimed = BookingReminder.objects.filter(
            booking_id=booking_id,
            sent_at__isnull=True,
        ).update(sent_at=now)
    return claimed == 1


def _recipient(booking):
    driver = getattr(booking.vehicle, "driver", None)
    user = getattr(driver, "user", None)
    return getattr(user, "email", None) or ""


def _subject():
    return "Бронь скоро заканчивается"


def _body(booking):
    code = getattr(booking.spot, "code", None) or "не указано"
    plate = getattr(booking.vehicle, "plate", None) or "не указан"
    when, zone = _local_end(booking.ends_at)
    return f"Место {code}. Номер {plate}. Окончание {when} ({zone})."


def _local_end(ends_at):
    tariff = (
        Tariff.objects.filter(effective_from__lte=ends_at)
        .order_by("-effective_from")
        .only("timezone")
        .first()
    )
    name = getattr(tariff, "timezone", None) or "UTC"
    try:
        zone = ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo("UTC")
        name = "UTC"
    return ends_at.astimezone(zone).strftime("%d.%m.%Y %H:%M"), name
