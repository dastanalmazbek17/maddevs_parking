"""Create, cancel, and expire bookings. No HTTP and no gate logic."""

from django.db import IntegrityError, transaction
from psycopg.errors import CheckViolation, ExclusionViolation

from apps.accounts.models import Vehicle
from apps.bookings.models import HOLDING_SPOT_STATUSES, Booking, BookingStatus
from apps.parking.constants import (
    BOOKING_START_GRACE,
    ENTRY_WINDOW,
    MAX_BOOKING_DURATION,
    MIN_BOOKING_DURATION,
)
from apps.parking.exceptions import (
    BookingConflict,
    BookingNotCancellable,
    BookingNotOwned,
    InvalidInterval,
    SpotNotFound,
    StartsInThePast,
    VehicleNotOwned,
    constraint_name,
    iter_causes,
)
from apps.parking.models import Spot
from apps.parking.services import resolve_now

_OVERLAP_CONSTRAINTS = frozenset(
    {"booking_no_overlap_per_spot", "booking_no_overlap_per_vehicle"}
)
_INTERVAL_CONSTRAINTS = frozenset(
    {"booking_duration_15m_to_24h", "booking_ends_after_start"}
)


def create_booking(driver, vehicle, spot, starts_at, ends_at, *, now=None):
    """Reserve `spot` for `vehicle`. The booking is free and starts active."""

    now = resolve_now(now)
    _validate_interval(starts_at, ends_at)
    if starts_at < now - BOOKING_START_GRACE:
        raise StartsInThePast("Booking cannot start more than 1 minute in the past.")

    with transaction.atomic():
        # Spot before vehicle, both by primary key, so two creates cannot deadlock.
        locked_spot = (
            Spot.objects.select_for_update(of=("self",))
            .filter(pk=getattr(spot, "pk", None))
            .first()
        )
        if locked_spot is None:
            raise SpotNotFound("Spot does not exist.")
        locked_vehicle = (
            Vehicle.objects.select_for_update(of=("self",))
            .filter(pk=getattr(vehicle, "pk", None))
            .first()
        )
        if locked_vehicle is None or locked_vehicle.driver_id != driver.pk:
            raise VehicleNotOwned("The vehicle belongs to another driver.")
        if _interval_taken(spot_id=locked_spot.pk, starts_at=starts_at, ends_at=ends_at):
            raise BookingConflict("The spot already has a booking in that interval.")
        if _interval_taken(vehicle_id=locked_vehicle.pk, starts_at=starts_at, ends_at=ends_at):
            raise BookingConflict("The vehicle already has a booking in that interval.")
        try:
            with transaction.atomic():
                return Booking.objects.create(
                    spot=locked_spot,
                    vehicle=locked_vehicle,
                    starts_at=starts_at,
                    ends_at=ends_at,
                    status=BookingStatus.ACTIVE,
                )
        except IntegrityError as exc:
            mapped = _as_domain_error(exc)
            if mapped is exc:
                raise
            raise mapped from exc


def cancel_booking(driver, booking, *, now=None):
    """Cancel an active booking. Cancelling an already cancelled one is a no-op."""

    resolve_now(now)
    with transaction.atomic():
        locked = Booking.objects.select_for_update(of=("self",)).get(pk=booking.pk)
        owner_id = Vehicle.objects.filter(pk=locked.vehicle_id).values_list("driver_id", flat=True).get()
        if owner_id != driver.pk:
            raise BookingNotOwned("The booking belongs to another driver.")
        if locked.status == BookingStatus.CANCELLED:
            return locked
        if locked.status != BookingStatus.ACTIVE:
            raise BookingNotCancellable("Only an active booking can be cancelled.")
        locked.status = BookingStatus.CANCELLED
        locked.save(update_fields=["status"])
        return locked


def expire_overdue_bookings(*, now=None):
    """Mark active bookings as expired once their entry window has closed.

    One conditional UPDATE, so a booking that was just checked in is left alone.
    Returns how many rows changed.
    """

    now = resolve_now(now)
    with transaction.atomic():
        return Booking.objects.filter(
            status=BookingStatus.ACTIVE,
            starts_at__lte=now - ENTRY_WINDOW,
        ).update(status=BookingStatus.EXPIRED)


def _validate_interval(starts_at, ends_at):
    if starts_at.tzinfo is None or starts_at.utcoffset() is None:
        raise InvalidInterval("starts_at must be timezone-aware.")
    if ends_at.tzinfo is None or ends_at.utcoffset() is None:
        raise InvalidInterval("ends_at must be timezone-aware.")
    if ends_at <= starts_at:
        raise InvalidInterval("ends_at must be after starts_at.")
    duration = ends_at - starts_at
    if duration < MIN_BOOKING_DURATION or duration > MAX_BOOKING_DURATION:
        raise InvalidInterval("Booking must last from 15 minutes to 24 hours.")


def _interval_taken(*, starts_at, ends_at, spot_id=None, vehicle_id=None):
    query = Booking.objects.filter(
        status__in=HOLDING_SPOT_STATUSES,
        starts_at__lt=ends_at,
        ends_at__gt=starts_at,
    )
    if spot_id is not None:
        query = query.filter(spot_id=spot_id)
    if vehicle_id is not None:
        query = query.filter(vehicle_id=vehicle_id)
    return query.exists()


def _as_domain_error(exc):
    causes = list(iter_causes(exc))
    name = constraint_name(exc)
    if any(isinstance(cause, ExclusionViolation) for cause in causes) or name in _OVERLAP_CONSTRAINTS:
        return BookingConflict("The spot or vehicle already has a booking in that interval.")
    if any(isinstance(cause, CheckViolation) for cause in causes) or name in _INTERVAL_CONSTRAINTS:
        return InvalidInterval("Booking interval is not allowed.")
    return exc
