"""Domain errors. HTTP status codes are chosen by the API, not here."""


class ParkingError(Exception):
    code = "parking_error"


class InvalidInterval(ParkingError):
    code = "invalid_interval"


class StartsInThePast(ParkingError):
    code = "starts_in_the_past"


class VehicleNotOwned(ParkingError):
    code = "vehicle_not_owned"


class SpotNotFound(ParkingError):
    code = "spot_not_found"


class BookingConflict(ParkingError):
    code = "booking_conflict"


class BookingNotOwned(ParkingError):
    code = "booking_not_owned"


class BookingNotCancellable(ParkingError):
    code = "booking_not_cancellable"


class DoubleEntry(ParkingError):
    code = "double_entry"


class NoFreePlace(ParkingError):
    code = "no_free_place"


class NoActiveVisit(ParkingError):
    code = "no_active_visit"


class InvalidPlate(ParkingError):
    code = "invalid_plate"


class ExitNotAfterEntry(ParkingError):
    code = "exit_not_after_entry"


def iter_causes(exc):
    cause = getattr(exc, "__cause__", None)
    seen = set()
    while cause is not None and id(cause) not in seen:
        seen.add(id(cause))
        yield cause
        cause = getattr(cause, "__cause__", None)


def constraint_name(exc):
    for cause in iter_causes(exc):
        diag = getattr(cause, "diag", None)
        if diag is not None and diag.constraint_name:
            return diag.constraint_name
    return ""
