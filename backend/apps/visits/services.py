"""Gate entry and exit. The plate is the only input; there is no HTTP here."""

from django.db import IntegrityError, transaction

from apps.accounts.models import Vehicle
from apps.accounts.plates import normalize_plate
from apps.bookings.models import Booking, BookingStatus
from apps.parking.constants import ENTRY_WINDOW
from apps.parking.exceptions import (
    BookingConflict,
    DoubleEntry,
    ExitNotAfterEntry,
    InvalidPlate,
    NoActiveVisit,
    NoFreePlace,
    SpotNotFound,
    constraint_name,
)
from apps.parking.models import Spot
from apps.parking.realtime import notify_spots_changed
from apps.parking.services import booking_holds_spot_q, resolve_now
from apps.tariffs.models import Tariff
from apps.tariffs.pricing import price_visit, tariff_from_row
from apps.visits.models import Invoice, Visit

_PLATE_CONSTRAINT = "visit_one_active_per_plate"
_SPOT_CONSTRAINT = "visit_one_active_per_spot"


class _SpotAlreadyTaken(Exception):
    """The partial unique index rejected this spot. Try another one."""


def enter(plate, *, now=None):
    """Let `plate` in. A matching booking is used only inside its entry window."""

    now = resolve_now(now)
    plate = _plate(plate)
    with transaction.atomic():
        _reject_active_visit(plate)
        # Read the booking before locking anything, then lock Spot -> Vehicle -> Booking.
        booking = _find_booking(plate, now)
        if booking is not None:
            visit = _enter_with_booking(booking, plate, now)
            if visit is not None:
                notify_spots_changed()
                return visit
        visit = _enter_without_booking(plate, now)
        notify_spots_changed()
        return visit


def exit_visit(plate, *, now=None):
    """Close the active visit, issue its invoice, and complete a checked-in booking."""

    now = resolve_now(now)
    plate = _plate(plate)
    with transaction.atomic():
        existing = Visit.objects.filter(plate=plate, exited_at__isnull=True).first()
        if existing is None:
            raise NoActiveVisit("This plate has no active visit.")
        # Booking before visit. The booking lock is skipped when the visit has none.
        booking = None
        if existing.booking_id is not None:
            booking = Booking.objects.select_for_update(of=("self",)).get(pk=existing.booking_id)
        visit = Visit.objects.select_for_update(of=("self",)).get(pk=existing.pk)
        if visit.exited_at is not None:
            raise NoActiveVisit("This plate has no active visit.")
        if now <= visit.entered_at:
            raise ExitNotAfterEntry("Exit must be after entry.")
        tariffs = [tariff_from_row(row) for row in Tariff.objects.all()]
        quote = price_visit(visit.entered_at, now, tariffs)
        visit.exited_at = now
        visit.save(update_fields=["exited_at"])
        invoice = Invoice.objects.create(
            visit=visit,
            amount_kopecks=quote.total_kopecks,
            issued_at=now,
        )
        if booking is not None and booking.status == BookingStatus.CHECKED_IN:
            booking.status = BookingStatus.COMPLETED
            booking.save(update_fields=["status"])
        notify_spots_changed()
        return visit, invoice


def _enter_with_booking(booking, plate, now):
    """Lock the booked spot, then the vehicle, then the booking, and recheck.

    Returns None when the booking can no longer be used, so the caller walks in.
    A taken spot is replaced by another free one; the booking row keeps its spot.
    """

    try:
        spot = Spot.objects.select_for_update(of=("self",)).get(pk=booking.spot_id)
    except Spot.DoesNotExist as exc:
        raise SpotNotFound("Spot does not exist.") from exc
    vehicle = Vehicle.objects.select_for_update(of=("self",)).get(pk=booking.vehicle_id)
    booking = Booking.objects.select_for_update(of=("self",)).get(pk=booking.pk)
    if booking.status != BookingStatus.ACTIVE or not _in_entry_window(booking, now):
        return None
    if not _spot_has_active_visit(spot.pk):
        try:
            visit = _insert_visit(
                spot,
                plate,
                now,
                driver_id=vehicle.driver_id,
                booking=booking,
            )
        except _SpotAlreadyTaken:
            visit = _take_free_spot(
                plate,
                now,
                driver_id=vehicle.driver_id,
                booking=booking,
            )
    else:
        visit = _take_free_spot(
            plate,
            now,
            driver_id=vehicle.driver_id,
            booking=booking,
        )
    booking.status = BookingStatus.CHECKED_IN
    booking.save(update_fields=["status"])
    return visit


def _enter_without_booking(plate, now):
    driver_id = Vehicle.objects.filter(plate=plate).values_list("driver_id", flat=True).first()
    return _take_free_spot(plate, now, driver_id=driver_id, booking=None)


def _take_free_spot(plate, now, *, driver_id, booking):
    """Lock one candidate spot at a time. A lost race tries the next spot."""

    tried = []
    while True:
        spot = _next_free_spot(now, exclude_ids=tried)
        if spot is None:
            raise NoFreePlace("No free spot is available.")
        try:
            return _insert_visit(spot, plate, now, driver_id=driver_id, booking=booking)
        except _SpotAlreadyTaken:
            tried.append(spot.pk)


def _next_free_spot(now, *, exclude_ids):
    occupied = Visit.objects.filter(exited_at__isnull=True).values("spot_id")
    held = Booking.objects.filter(booking_holds_spot_q(now)).values("spot_id")
    # A checked-in booking keeps its original spot until ends_at, even after the
    # car was sent somewhere else. The map does not paint that spot as booked.
    kept = Booking.objects.filter(
        status=BookingStatus.CHECKED_IN,
        ends_at__gt=now,
    ).values("spot_id")
    return (
        Spot.objects.select_for_update(skip_locked=True, of=("self",))
        .exclude(pk__in=occupied)
        .exclude(pk__in=held)
        .exclude(pk__in=kept)
        .exclude(pk__in=exclude_ids)
        .order_by("pk")
        .first()
    )


def _insert_visit(spot, plate, now, *, driver_id, booking):
    try:
        with transaction.atomic():
            return Visit.objects.create(
                spot=spot,
                driver_id=driver_id,
                booking=booking,
                plate=plate,
                entered_at=now,
            )
    except IntegrityError as exc:
        name = constraint_name(exc)
        if name == _PLATE_CONSTRAINT:
            raise DoubleEntry("This plate already has an active visit.") from exc
        if name == _SPOT_CONSTRAINT:
            raise _SpotAlreadyTaken from exc
        raise


def _reject_active_visit(plate):
    active = (
        Visit.objects.select_for_update(of=("self",))
        .filter(plate=plate, exited_at__isnull=True)
        .first()
    )
    if active is not None:
        raise DoubleEntry("This plate already has an active visit.")


def _find_booking(plate, now):
    matches = list(
        Booking.objects.filter(
            status=BookingStatus.ACTIVE,
            vehicle__plate=plate,
            starts_at__lte=now,
            starts_at__gt=now - ENTRY_WINDOW,
        ).order_by("pk")[:2]
    )
    if not matches:
        return None
    if len(matches) > 1:
        raise BookingConflict("More than one booking matches this plate.")
    return matches[0]


def _in_entry_window(booking, now):
    return booking.starts_at <= now < booking.starts_at + ENTRY_WINDOW


def _spot_has_active_visit(spot_id):
    return Visit.objects.filter(spot_id=spot_id, exited_at__isnull=True).exists()


def _plate(value):
    normalized = normalize_plate(value)
    if not normalized:
        raise InvalidPlate("Plate is empty.")
    return normalized
