"""JSON field shapes shared by the HTTP layer. No business rules."""

from datetime import timezone


def isoformat_utc(value):
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def visit_payload(visit):
    return {
        "id": visit.pk,
        "plate": visit.plate,
        "spot_code": visit.spot.code,
        "entered_at": isoformat_utc(visit.entered_at),
        "booking_id": visit.booking_id,
    }


def invoice_payload(invoice):
    return {
        "total_kopecks": invoice.amount_kopecks,
        "issued_at": isoformat_utc(invoice.issued_at),
    }
