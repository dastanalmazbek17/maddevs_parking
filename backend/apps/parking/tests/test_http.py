"""HTTP API: registration, login, and the shared error shape."""

import pytest
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
