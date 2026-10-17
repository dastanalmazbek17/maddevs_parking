"""Turn domain and validation errors into one JSON shape.

Unknown failures are logged and replaced with a generic 500. The client
never receives a traceback.
"""

import logging

from django.http import Http404
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from apps.parking.exceptions import ParkingError

logger = logging.getLogger(__name__)

PARKING_STATUS = {
    "invalid_interval": 400,
    "starts_in_the_past": 400,
    "invalid_plate": 400,
    "vehicle_not_owned": 404,
    "booking_not_owned": 404,
    "spot_not_found": 404,
    "booking_conflict": 409,
    "booking_not_cancellable": 409,
    "double_entry": 409,
    "no_free_place": 409,
    "no_active_visit": 409,
    "exit_not_after_entry": 409,
}

PARKING_DETAIL = {
    "invalid_interval": "Интервал брони недопустим.",
    "starts_in_the_past": "Бронь не может начинаться в прошлом.",
    "invalid_plate": "Номер машины указан неверно.",
    "vehicle_not_owned": "Машина не найдена.",
    "booking_not_owned": "Бронь не найдена.",
    "spot_not_found": "Место не найдено.",
    "booking_conflict": "Это время уже занято.",
    "booking_not_cancellable": "Эту бронь нельзя отменить.",
    "double_entry": "Эта машина уже на парковке.",
    "no_free_place": "Свободных мест нет.",
    "no_active_visit": "Активный визит не найден.",
    "exit_not_after_entry": "Выезд должен быть позже заезда.",
}


def api_exception_handler(exc, context):
    if isinstance(exc, ParkingError):
        code = exc.code
        return Response(
            {"code": code, "detail": PARKING_DETAIL.get(code, "Ошибка запроса.")},
            status=PARKING_STATUS.get(code, 400),
        )

    if isinstance(exc, DRFValidationError):
        return Response(_validation_body(exc), status=400)

    if isinstance(exc, Http404):
        return Response({"code": "not_found", "detail": "Не найдено."}, status=404)

    response = drf_exception_handler(exc, context)
    if response is not None:
        status_code = response.status_code
        if status_code == 401:
            return Response(
                {"code": "not_authenticated", "detail": "Нужна авторизация."},
                status=401,
            )
        if status_code == 404:
            return Response({"code": "not_found", "detail": "Не найдено."}, status=404)
        return response

    logger.exception("Unhandled API error")
    return Response(
        {"code": "server_error", "detail": "Внутренняя ошибка сервера."},
        status=500,
    )


def _validation_body(exc):
    detail = exc.detail
    fields = {}
    if isinstance(detail, dict):
        fields = {str(key): _flatten(value) for key, value in detail.items()}
        text = "Проверьте поля запроса."
    else:
        text = _flatten(detail)
    return {"code": "validation_error", "detail": text, "fields": fields}


def _flatten(value):
    if isinstance(value, dict):
        return " ".join(f"{key}: {_flatten(item)}" for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return " ".join(_flatten(item) for item in value)
    return str(value)
