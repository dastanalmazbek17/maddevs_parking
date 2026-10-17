import re

from django.utils import timezone
from rest_framework import serializers

_OFFSET = re.compile(r"(?:Z|[+-]\d{2}:?\d{2})$", re.IGNORECASE)


class AwareDateTimeField(serializers.DateTimeField):
    """Reject clock times that do not carry a timezone."""

    def to_internal_value(self, value):
        if isinstance(value, str) and _OFFSET.search(value.strip()) is None:
            raise serializers.ValidationError("Укажите время в ISO 8601 с часовым поясом.")
        parsed = super().to_internal_value(value)
        if timezone.is_naive(parsed):
            raise serializers.ValidationError("Укажите время в ISO 8601 с часовым поясом.")
        return parsed


class BookingCreateSerializer(serializers.Serializer):
    vehicle = serializers.IntegerField(min_value=1)
    spot = serializers.IntegerField(min_value=1)
    starts_at = AwareDateTimeField()
    ends_at = AwareDateTimeField()
