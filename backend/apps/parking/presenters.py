"""JSON field shapes shared by the HTTP layer. No business rules."""

from datetime import timezone


def isoformat_utc(value):
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
