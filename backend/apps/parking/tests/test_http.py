"""HTTP API: auth, vehicles, spots, bookings, history, and the gate."""

import os
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from django.contrib.auth import authenticate, get_user_model
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.accounts.models import Vehicle
from apps.bookings.models import Booking, BookingStatus
from apps.parking.models import Spot
from apps.tariffs.models import Tariff
from apps.tariffs.pricing import price_visit, tariff_from_row
from apps.visits.models import Invoice, Visit
from config.exception_handler import api_exception_handler

User = get_user_model()
pytestmark = pytest.mark.django_db

PASSWORD = "secret-pass"


def _client():
    return APIClient()


def _iso(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _register(client, email, password=PASSWORD):
    response = client.post(
        "/api/auth/register/",
        {"email": email, "password": password},
        format="json",
    )
    assert response.status_code == 201, response.data
    client.credentials(HTTP_AUTHORIZATION=f"Token {response.data['token']}")
    return response.data


def _spot(code="A1"):
    return Spot.objects.create(code=code)


def _book(client, vehicle_id, spot_id, start, end):
    return client.post(
        "/api/bookings/",
        {
            "vehicle": vehicle_id,
            "spot": spot_id,
            "starts_at": _iso(start),
            "ends_at": _iso(end),
        },
        format="json",
    )


def test_unknown_error_hides_the_traceback():
    response = api_exception_handler(RuntimeError("secret-token"), None)
    assert response.status_code == 500
    assert response.data == {
        "code": "server_error",
        "detail": "Внутренняя ошибка сервера.",
    }
    assert "secret-token" not in str(response.data)


def test_health_is_public_and_uses_one_query():
    client = _client()
    with CaptureQueriesContext(connection) as captured:
        response = client.get("/api/health/")
    assert response.status_code == 200
    assert response.data == {"status": "ok"}
    assert len(captured) == 1


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


def test_vehicle_delete_is_scoped_and_blocked_while_the_car_is_in_use():
    owner = _client()
    _register(owner, "owner@example.com")
    own = owner.post("/api/vehicles/", {"plate": "OWN111"}, format="json").data
    busy = owner.post("/api/vehicles/", {"plate": "BUSY11"}, format="json").data
    other = _client()
    _register(other, "other@example.com")
    foreign = other.post("/api/vehicles/", {"plate": "THEIR1"}, format="json").data

    missing = owner.delete("/api/vehicles/999999/")
    stolen = owner.delete(f"/api/vehicles/{foreign['id']}/")
    assert missing.status_code == 404
    assert missing.data == stolen.data
    assert stolen.data["code"] == "not_found"
    assert Vehicle.objects.filter(pk=foreign["id"]).exists()

    spot = _spot()
    start = datetime.now(timezone.utc) + timedelta(hours=2)
    booked = _book(owner, busy["id"], spot.pk, start, start + timedelta(hours=1))
    assert booked.status_code == 201, booked.data
    blocked = owner.delete(f"/api/vehicles/{busy['id']}/")
    assert blocked.status_code == 409
    assert blocked.data["code"] == "vehicle_in_use"

    removed = owner.delete(f"/api/vehicles/{own['id']}/")
    assert removed.status_code == 204
    assert not Vehicle.objects.filter(pk=own["id"]).exists()

    anonymous = _client()
    assert anonymous.delete(f"/api/vehicles/{foreign['id']}/").status_code == 401


def test_finished_booking_still_blocks_delete_because_the_row_is_protected():
    owner = _client()
    _register(owner, "owner@example.com")
    vehicle = owner.post("/api/vehicles/", {"plate": "DONE11"}, format="json").data
    spot = _spot()
    start = datetime.now(timezone.utc) + timedelta(hours=3)
    booked = _book(owner, vehicle["id"], spot.pk, start, start + timedelta(hours=1))
    assert booked.status_code == 201
    cancelled = owner.post(f"/api/bookings/{booked.data['id']}/cancel/")
    assert cancelled.status_code == 200
    blocked = owner.delete(f"/api/vehicles/{vehicle['id']}/")
    assert blocked.status_code == 409
    assert blocked.data["code"] == "vehicle_in_use"


def test_spots_are_public_and_one_query_covers_every_spot():
    free = _spot("F1")
    held = _spot("H1")
    taken = _spot("T1")
    driver = _client()
    _register(driver, "spots@example.com")
    vehicle = driver.post("/api/vehicles/", {"plate": "SPOT01"}, format="json").data
    start = datetime.now(timezone.utc)
    booked = _book(driver, vehicle["id"], held.pk, start, start + timedelta(hours=1))
    assert booked.status_code == 201, booked.data
    Visit.objects.create(
        spot=taken,
        plate="WALK01",
        entered_at=start,
    )

    client = _client()
    with CaptureQueriesContext(connection) as captured:
        response = client.get("/api/spots/")
    assert response.status_code == 200
    assert len(captured) == 1
    by_code = {row["code"]: row for row in response.data}
    assert by_code[free.code]["status"] == "free"
    assert by_code[held.code]["status"] == "booked"
    assert by_code[taken.code]["status"] == "occupied"
    assert by_code[free.code]["id"] == free.pk


def test_bookings_require_a_token_and_reject_bad_input():
    anonymous = _client()
    assert anonymous.get("/api/bookings/").status_code == 401
    assert anonymous.post("/api/bookings/", {}, format="json").status_code == 401

    driver = _client()
    _register(driver, "book@example.com")
    vehicle = driver.post("/api/vehicles/", {"plate": "BOOK01"}, format="json").data
    spot = _spot()
    start = datetime.now(timezone.utc) + timedelta(hours=2)
    naive = driver.post(
        "/api/bookings/",
        {
            "vehicle": vehicle["id"],
            "spot": spot.pk,
            "starts_at": "2026-10-18T10:00:00",
            "ends_at": "2026-10-18T11:00:00",
        },
        format="json",
    )
    assert naive.status_code == 400
    assert naive.data["code"] == "validation_error"
    assert "starts_at" in naive.data["fields"]

    past = _book(
        driver,
        vehicle["id"],
        spot.pk,
        start - timedelta(days=2),
        start - timedelta(days=2) + timedelta(hours=1),
    )
    assert past.status_code == 400
    assert past.data["code"] == "starts_in_the_past"

    short = _book(driver, vehicle["id"], spot.pk, start, start + timedelta(minutes=10))
    assert short.status_code == 400
    assert short.data["code"] == "invalid_interval"

    missing_spot = _book(driver, vehicle["id"], 999999, start, start + timedelta(hours=1))
    assert missing_spot.status_code == 404
    assert missing_spot.data["code"] == "spot_not_found"

    missing_vehicle = _book(driver, 999999, spot.pk, start, start + timedelta(hours=1))
    assert missing_vehicle.status_code == 404
    assert missing_vehicle.data["code"] == "vehicle_not_owned"

    other = _client()
    _register(other, "other-car@example.com")
    foreign_vehicle = other.post("/api/vehicles/", {"plate": "OTHER1"}, format="json").data
    foreign = _book(driver, foreign_vehicle["id"], spot.pk, start, start + timedelta(hours=1))
    assert foreign.status_code == 404
    assert foreign.data == missing_vehicle.data

    unknown = driver.get("/api/bookings/?status=nope")
    assert unknown.status_code == 400
    assert unknown.data["code"] == "validation_error"


def test_other_driver_cannot_see_or_cancel_a_booking():
    owner = _client()
    _register(owner, "owner@example.com")
    vehicle = owner.post("/api/vehicles/", {"plate": "MINE01"}, format="json").data
    spot = _spot()
    start = datetime.now(timezone.utc) + timedelta(hours=4)
    created = _book(owner, vehicle["id"], spot.pk, start, start + timedelta(hours=1))
    assert created.status_code == 201, created.data
    booking_id = created.data["id"]

    other = _client()
    _register(other, "other@example.com")
    listed = other.get("/api/bookings/")
    assert listed.status_code == 200
    assert listed.data["results"] == []

    missing = other.post("/api/bookings/999999/cancel/")
    forbidden = other.post(f"/api/bookings/{booking_id}/cancel/")
    assert missing.status_code == 404
    assert forbidden.status_code == 404
    assert forbidden.data == missing.data
    assert forbidden.data["code"] == "not_found"
    assert Booking.objects.get(pk=booking_id).status == BookingStatus.ACTIVE

    cancelled = owner.post(f"/api/bookings/{booking_id}/cancel/")
    assert cancelled.status_code == 200
    assert cancelled.data["status"] == "cancelled"
    again = owner.post(f"/api/bookings/{booking_id}/cancel/")
    assert again.status_code == 200
    assert again.data["status"] == "cancelled"

    only_cancelled = owner.get("/api/bookings/?status=cancelled")
    assert [row["id"] for row in only_cancelled.data["results"]] == [booking_id]
    assert owner.get("/api/bookings/?status=active").data["results"] == []


def test_booking_conflict_and_pagination():
    driver = _client()
    _register(driver, "pages@example.com")
    vehicle = driver.post("/api/vehicles/", {"plate": "PAGE01"}, format="json").data
    spot = _spot()
    start = datetime.now(timezone.utc) + timedelta(days=1)
    first = _book(driver, vehicle["id"], spot.pk, start, start + timedelta(minutes=15))
    assert first.status_code == 201
    overlap = _book(
        driver,
        vehicle["id"],
        spot.pk,
        start + timedelta(minutes=5),
        start + timedelta(minutes=20),
    )
    assert overlap.status_code == 409
    assert overlap.data["code"] == "booking_conflict"

    for index in range(1, 21):
        begin = start + timedelta(minutes=15 * index)
        created = _book(driver, vehicle["id"], spot.pk, begin, begin + timedelta(minutes=15))
        assert created.status_code == 201, created.data

    page = driver.get("/api/bookings/")
    assert page.status_code == 200
    assert page.data["count"] == 21
    assert len(page.data["results"]) == 20
    assert page.data["next"]
    assert page.data["results"][0]["id"] > page.data["results"][1]["id"]


def test_checked_in_booking_cannot_be_cancelled():
    driver = _client()
    _register(driver, "stay@example.com")
    vehicle = driver.post("/api/vehicles/", {"plate": "STAY01"}, format="json").data
    spot = _spot()
    start = datetime.now(timezone.utc)
    created = _book(driver, vehicle["id"], spot.pk, start, start + timedelta(hours=1))
    assert created.status_code == 201, created.data
    entered = _client().post("/api/gate/enter/", {"plate": "stay01"}, format="json")
    assert entered.status_code == 201, entered.data
    assert entered.data["booking_id"] == created.data["id"]
    denied = driver.post(f"/api/bookings/{created.data['id']}/cancel/")
    assert denied.status_code == 409
    assert denied.data["code"] == "booking_not_cancellable"


def test_gate_is_public_and_reports_entry_conflicts():
    anonymous = _client()
    assert anonymous.post("/api/gate/enter/", {}, format="json").status_code == 400
    empty = anonymous.post("/api/gate/enter/", {"plate": " - "}, format="json")
    assert empty.status_code == 400
    assert empty.data["code"] == "invalid_plate"
    nowhere = anonymous.post("/api/gate/exit/", {"plate": "NONE01"}, format="json")
    assert nowhere.status_code == 409
    assert nowhere.data["code"] == "no_active_visit"
    full = anonymous.post("/api/gate/enter/", {"plate": "FULL01"}, format="json")
    assert full.status_code == 409
    assert full.data["code"] == "no_free_place"

    _spot("G1")
    first = anonymous.post("/api/gate/enter/", {"plate": "А777АА"}, format="json")
    assert first.status_code == 201
    assert first.data["plate"] == "A777AA"
    assert first.data["booking_id"] is None
    assert first.data["spot_code"] == "G1"
    second = anonymous.post("/api/gate/enter/", {"plate": "a777aa"}, format="json")
    assert second.status_code == 409
    assert second.data["code"] == "double_entry"


def test_exit_at_the_entry_instant_is_409():
    _spot("E1")
    frozen = datetime(2026, 6, 1, 4, 0, tzinfo=timezone.utc)
    driver = _client()
    _register(driver, "frozen@example.com")
    vehicle = driver.post("/api/vehicles/", {"plate": "FRZN01"}, format="json").data
    spot = Spot.objects.get(code="E1")
    with patch("django.utils.timezone.now", return_value=frozen):
        created = _book(driver, vehicle["id"], spot.pk, frozen, frozen + timedelta(hours=1))
        assert created.status_code == 201, created.data
        entered = _client().post("/api/gate/enter/", {"plate": "FRZN01"}, format="json")
        assert entered.status_code == 201, entered.data
        exited = _client().post("/api/gate/exit/", {"plate": "FRZN01"}, format="json")
    assert exited.status_code == 409
    assert exited.data["code"] == "exit_not_after_entry"
    assert Visit.objects.get(plate="FRZN01").exited_at is None
    assert Invoice.objects.count() == 0


def test_driver_books_enters_exits_and_reads_one_invoice():
    driver = _client()
    _register(driver, "flow@example.com")
    vehicle = driver.post("/api/vehicles/", {"plate": "flow01"}, format="json").data
    spot = _spot("FLOW")
    start = datetime.now(timezone.utc)
    created = _book(driver, vehicle["id"], spot.pk, start, start + timedelta(hours=1))
    assert created.status_code == 201, created.data

    gate = _client()
    entered = gate.post("/api/gate/enter/", {"plate": "FLOW01"}, format="json")
    assert entered.status_code == 201, entered.data
    assert entered.data["booking_id"] == created.data["id"]
    assert entered.data["spot_code"] == "FLOW"

    time.sleep(0.05)
    exited = gate.post("/api/gate/exit/", {"plate": "FLOW01"}, format="json")
    assert exited.status_code == 200, exited.data
    invoice = exited.data["invoice"]
    visit = exited.data["visit"]
    entered_at = datetime.fromisoformat(visit["entered_at"].replace("Z", "+00:00"))
    exited_at = datetime.fromisoformat(visit["exited_at"].replace("Z", "+00:00"))
    tariffs = [tariff_from_row(row) for row in Tariff.objects.all()]
    assert invoice["total_kopecks"] == price_visit(entered_at, exited_at, tariffs).total_kopecks
    assert type(invoice["total_kopecks"]) is int

    history = driver.get("/api/visits/")
    assert history.status_code == 200
    assert history.data["count"] == 1
    assert history.data["results"][0]["invoice"]["total_kopecks"] == invoice["total_kopecks"]
    bills = driver.get("/api/invoices/")
    assert bills.status_code == 200
    assert bills.data["results"][0]["total_kopecks"] == invoice["total_kopecks"]
    assert bills.data["results"][0]["visit_id"] == visit["id"]

    other = _client()
    _register(other, "outsider@example.com")
    assert other.get("/api/visits/").data["results"] == []
    assert other.get("/api/invoices/").data["results"] == []

    repeat = gate.post("/api/gate/exit/", {"plate": "FLOW01"}, format="json")
    assert repeat.status_code == 409
    assert repeat.data["code"] == "no_active_visit"
    assert Invoice.objects.count() == 1


def test_history_requires_a_token():
    assert _client().get("/api/visits/").status_code == 401
    assert _client().get("/api/invoices/").status_code == 401


def test_seed_demo_can_run_twice():
    call_command("seed_demo")
    spots = Spot.objects.filter(code__in=[f"P{number:02d}" for number in range(1, 13)]).count()
    users = User.objects.filter(email="demo@example.com").count()
    vehicles = Vehicle.objects.filter(plate="A000AA").count()
    tariffs = Tariff.objects.filter(effective_from=datetime(2020, 1, 1, tzinfo=timezone.utc)).count()
    call_command("seed_demo")
    assert spots == 12
    assert users == 1
    assert vehicles == 1
    assert tariffs == 1
    assert Spot.objects.filter(code__in=[f"P{number:02d}" for number in range(1, 13)]).count() == 12
    assert User.objects.filter(email="demo@example.com").count() == 1
    assert Vehicle.objects.filter(plate="A000AA").count() == 1
    assert Tariff.objects.filter(effective_from=datetime(2020, 1, 1, tzinfo=timezone.utc)).count() == 1
    password = os.environ.get("DEMO_PASSWORD") or "ParkDemo-2026"
    assert authenticate(email="demo@example.com", password=password) is not None
