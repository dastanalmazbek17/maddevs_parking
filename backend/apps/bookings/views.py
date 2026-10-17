from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Driver, Vehicle
from apps.bookings.models import Booking, BookingStatus
from apps.bookings.serializers import BookingCreateSerializer
from apps.bookings.services import cancel_booking, create_booking
from apps.parking.models import Spot
from apps.parking.presenters import isoformat_utc


class BookingPagination(PageNumberPagination):
    page_size = 20


def _driver(user):
    return get_object_or_404(Driver, user=user)


def _booking_payload(booking):
    return {
        "id": booking.pk,
        "vehicle_id": booking.vehicle_id,
        "spot_id": booking.spot_id,
        "spot_code": booking.spot.code,
        "starts_at": isoformat_utc(booking.starts_at),
        "ends_at": isoformat_utc(booking.ends_at),
        "status": booking.status,
        "created_at": isoformat_utc(booking.created_at),
    }


class BookingListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        driver = _driver(request.user)
        chosen = request.query_params.get("status")
        if chosen is not None and chosen not in BookingStatus.values:
            raise ValidationError({"status": "Неизвестный статус."})
        bookings = (
            Booking.objects.filter(vehicle__driver=driver)
            .select_related("spot")
            .order_by("-created_at", "-pk")
        )
        if chosen is not None:
            bookings = bookings.filter(status=chosen)
        paginator = BookingPagination()
        page = paginator.paginate_queryset(bookings, request, view=self)
        return paginator.get_paginated_response([_booking_payload(booking) for booking in page])

    def post(self, request):
        driver = _driver(request.user)
        serializer = BookingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        booking = create_booking(
            driver,
            Vehicle(pk=data["vehicle"]),
            Spot(pk=data["spot"]),
            data["starts_at"],
            data["ends_at"],
        )
        booking = Booking.objects.select_related("spot").get(pk=booking.pk)
        return Response(_booking_payload(booking), status=status.HTTP_201_CREATED)


class BookingCancelView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        driver = _driver(request.user)
        booking = get_object_or_404(
            Booking.objects.select_related("spot"),
            pk=pk,
            vehicle__driver=driver,
        )
        booking = cancel_booking(driver, booking)
        return Response(_booking_payload(booking))
