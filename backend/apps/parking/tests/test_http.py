"""HTTP API: registration, login, vehicles, and the spot board."""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from config.exception_handler import api_exception_handler

pytestmark = pytest.mark.django_db

PASSWORD = "secret-pass"


def _client():
    return APIClient()


def _register(client, email, password=PASSWORD):
    response = client.post(
        "/api/auth/register/",
        {"email": email, "password": password},
        format="json",
    )
    assert response.status_code == 201, response.data
    client.credentials(HTTP_AUTHORIZATION=f"Token {response.data['token']}")
    return response.data


def test_unknown_error_hides_the_traceback():
    response = api_exception_handler(RuntimeError("secret-token"), None)
    assert response.status_code == 500
    assert response.data == {
        "code": "server_error",
        "detail": "Внутренняя ошибка сервера.",
    }
    assert "secret-token" not in str(response.data)


def test_register_normalizes_email_and_rejects_duplicates_and_weak_passwords():
    client = _client()
    created = _register(client, "A@x.com")
    assert created["email"] == "a@x.com"
    assert created["token"]

    again = client.post(
        "/api/auth/register/",
        {"email": "a@x.COM", "password": PASSWORD},
        format="json",
    )
    assert again.status_code == 400
    assert again.data["code"] == "validation_error"
    assert "почтой" in again.data["fields"]["email"]

    weak = _client().post(
        "/api/auth/register/",
        {"email": "new@x.com", "password": "short"},
        format="json",
    )
    assert weak.status_code == 400
    assert weak.data["code"] == "validation_error"
    assert "password" in weak.data["fields"]


def test_login_hides_which_field_was_wrong():
    client = _client()
    registered = _register(client, "driver@example.com")
    fresh = _client()
    wrong_password = fresh.post(
        "/api/auth/login/",
        {"email": "driver@example.com", "password": "wrong-pass-1"},
        format="json",
    )
    wrong_email = fresh.post(
        "/api/auth/login/",
        {"email": "missing@example.com", "password": PASSWORD},
        format="json",
    )
    assert wrong_password.status_code == 400
    assert wrong_password.data == wrong_email.data
    assert wrong_password.data["code"] == "invalid_credentials"

    logged_in = fresh.post(
        "/api/auth/login/",
        {"email": "DRIVER@example.com", "password": PASSWORD},
        format="json",
    )
    assert logged_in.status_code == 200
    assert logged_in.data["token"] == registered["token"]


def test_health_is_public_and_uses_one_query():
    client = _client()
    with CaptureQueriesContext(connection) as captured:
        response = client.get("/api/health/")
    assert response.status_code == 200
    assert response.data == {"status": "ok"}
    assert len(captured) == 1


def test_me_and_vehicles_require_a_token_and_normalize_the_plate():
    anonymous = _client()
    assert anonymous.get("/api/me/").status_code == 401
    assert anonymous.get("/api/me/").data["code"] == "not_authenticated"
    assert anonymous.post("/api/vehicles/", {"plate": "A111AA"}, format="json").status_code == 401

    owner = _client()
    _register(owner, "owner@example.com")
    me = owner.get("/api/me/")
    assert me.status_code == 200
    assert me.data["email"] == "owner@example.com"
    assert me.data["vehicles"] == []

    created = owner.post("/api/vehicles/", {"plate": "а 123-вс"}, format="json")
    assert created.status_code == 201
    assert created.data["plate"] == "A123BC"
    listed = owner.get("/api/vehicles/")
    assert listed.status_code == 200
    assert listed.data == [created.data]
    assert owner.get("/api/me/").data["vehicles"] == [created.data]

    blank = owner.post("/api/vehicles/", {"plate": "---"}, format="json")
    assert blank.status_code == 400
    assert blank.data["code"] == "invalid_plate"


def test_duplicate_plate_is_409_and_does_not_name_the_owner():
    first = _client()
    _register(first, "first@example.com")
    created = first.post("/api/vehicles/", {"plate": "A123BC"}, format="json")
    assert created.status_code == 201

    second = _client()
    _register(second, "second@example.com")
    conflict = second.post("/api/vehicles/", {"plate": "А123ВС"}, format="json")
    assert conflict.status_code == 409
    assert conflict.data["code"] == "plate_taken"
    assert "first@example.com" not in str(conflict.data)
