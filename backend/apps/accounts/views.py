from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Driver, Vehicle
from apps.accounts.serializers import LoginSerializer, RegisterSerializer, VehicleCreateSerializer
from apps.accounts.services import login, register
from apps.bookings.models import HOLDING_SPOT_STATUSES
from apps.visits.models import Visit

User = get_user_model()

_DUPLICATE_EMAIL = {
    "code": "validation_error",
    "detail": "Проверьте поля запроса.",
    "fields": {"email": "Пользователь с такой почтой уже есть."},
}
_INVALID_LOGIN = {
    "code": "invalid_credentials",
    "detail": "Неверная почта или пароль.",
}
_PLATE_TAKEN = {
    "code": "plate_taken",
    "detail": "Такой номер уже зарегистрирован.",
}
_VEHICLE_IN_USE = {
    "code": "vehicle_in_use",
    "detail": "Машину нельзя удалить: есть бронь или незакрытый визит.",
}


def _driver(user):
    return get_object_or_404(Driver, user=user)


def _vehicle_payload(vehicle):
    return {"id": vehicle.pk, "plate": vehicle.plate}


class RegisterView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                user, token = register(**serializer.validated_data)
        except IntegrityError:
            return Response(_DUPLICATE_EMAIL, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"email": user.email, "token": token.key},
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = login(**serializer.validated_data)
        if result is None:
            return Response(_INVALID_LOGIN, status=status.HTTP_400_BAD_REQUEST)
        _user, token = result
        return Response({"token": token.key})


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        driver = _driver(request.user)
        vehicles = driver.vehicles.order_by("pk")
        return Response(
            {
                "email": request.user.email,
                "vehicles": [_vehicle_payload(vehicle) for vehicle in vehicles],
            }
        )


class VehicleListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        driver = _driver(request.user)
        vehicles = driver.vehicles.order_by("pk")
        return Response([_vehicle_payload(vehicle) for vehicle in vehicles])

    def post(self, request):
        driver = _driver(request.user)
        serializer = VehicleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                vehicle = Vehicle.objects.create(
                    driver=driver,
                    plate=serializer.validated_data["plate"],
                )
        except IntegrityError:
            return Response(_PLATE_TAKEN, status=status.HTTP_409_CONFLICT)
        return Response(_vehicle_payload(vehicle), status=status.HTTP_201_CREATED)


class VehicleDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        driver = _driver(request.user)
        vehicle = get_object_or_404(Vehicle, pk=pk, driver=driver)
        held = vehicle.bookings.filter(status__in=HOLDING_SPOT_STATUSES).exists()
        open_visit = Visit.objects.filter(plate=vehicle.plate, exited_at__isnull=True).exists()
        if held or open_visit:
            return Response(_VEHICLE_IN_USE, status=status.HTTP_409_CONFLICT)
        try:
            vehicle.delete()
        except ProtectedError:
            return Response(_VEHICLE_IN_USE, status=status.HTTP_409_CONFLICT)
        return Response(status=status.HTTP_204_NO_CONTENT)
