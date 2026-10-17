from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.accounts.plates import normalize_plate
from apps.parking.exceptions import InvalidPlate


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class VehicleCreateSerializer(serializers.Serializer):
    plate = serializers.CharField()

    def validate_plate(self, value):
        normalized = normalize_plate(value)
        if not normalized:
            raise InvalidPlate("Номер машины указан неверно.")
        return normalized
