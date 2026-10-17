"""Database constraints for bookings and visits, checked through the ORM."""

from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.accounts.models import Driver, Vehicle
from apps.accounts.plates import normalize_plate
from apps.bookings.models import Booking, BookingStatus
from apps.notifications.models import BookingReminder
from apps.parking.models import Spot
from apps.tariffs.models import Tariff
from apps.visits.models import Invoice, Visit

User = get_user_model()


class DatabaseConstraintTests(TestCase):
    def setUp(self):
        self.spot = Spot.objects.create(code="A1")
        self.other_spot = Spot.objects.create(code="A2")
        self.driver = self._driver("driver@example.com")
        self.vehicle = Vehicle.objects.create(driver=self.driver, plate="A123BC01")
        self.other_vehicle = Vehicle.objects.create(driver=self.driver, plate="B456DE02")
        self.starts_at = timezone.now().replace(microsecond=0)

    def _driver(self, email):
        user = User.objects.create_user(username=email, email=email, password="secret")
        return Driver.objects.create(user=user)

    def _booking(self, *, spot, start, end, status=BookingStatus.ACTIVE, vehicle=None):
        return Booking.objects.create(
            spot=spot,
            vehicle=vehicle or self.vehicle,
            starts_at=start,
            ends_at=end,
            status=status,
        )

    def test_holding_bookings_for_one_spot_cannot_overlap(self):
        self._booking(
            spot=self.spot,
            start=self.starts_at,
            end=self.starts_at + timedelta(hours=2),
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._booking(
                    spot=self.spot,
                    start=self.starts_at + timedelta(hours=1),
                    end=self.starts_at + timedelta(hours=3),
                    status=BookingStatus.CHECKED_IN,
                )

        self._booking(
            spot=self.spot,
            start=self.starts_at,
            end=self.starts_at + timedelta(hours=2),
            status=BookingStatus.CANCELLED,
        )
        self._booking(
            spot=self.spot,
            start=self.starts_at,
            end=self.starts_at + timedelta(hours=2),
            status=BookingStatus.EXPIRED,
        )
        self._booking(
            spot=self.spot,
            start=self.starts_at,
            end=self.starts_at + timedelta(hours=2),
            status=BookingStatus.COMPLETED,
        )
        self._booking(
            spot=self.spot,
            start=self.starts_at + timedelta(hours=2),
            end=self.starts_at + timedelta(hours=3),
        )

    def test_booking_duration_is_from_15_minutes_to_24_hours(self):
        self._booking(
            spot=self.spot,
            start=self.starts_at,
            end=self.starts_at + timedelta(minutes=15),
        )
        self._booking(
            spot=self.other_spot,
            start=self.starts_at,
            end=self.starts_at + timedelta(hours=24),
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._booking(
                    spot=self.spot,
                    start=self.starts_at + timedelta(hours=1),
                    end=self.starts_at + timedelta(hours=1, minutes=14),
                )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._booking(
                    spot=self.spot,
                    start=self.starts_at + timedelta(days=2),
                    end=self.starts_at + timedelta(days=2, hours=24, minutes=1),
                )

    def test_one_plate_cannot_have_two_active_visits(self):
        visit = Visit.objects.create(
            spot=self.spot,
            plate="A123BC01",
            entered_at=self.starts_at,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Visit.objects.create(
                    spot=self.other_spot,
                    plate="A123BC01",
                    entered_at=self.starts_at + timedelta(minutes=5),
                )

        visit.exited_at = self.starts_at + timedelta(minutes=30)
        visit.save(update_fields=["exited_at"])

        Visit.objects.create(
            spot=self.other_spot,
            plate="A123BC01",
            entered_at=self.starts_at + timedelta(minutes=31),
        )

    def test_one_spot_cannot_have_two_active_visits(self):
        Visit.objects.create(
            spot=self.spot,
            plate="A123BC01",
            entered_at=self.starts_at,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Visit.objects.create(
                    spot=self.spot,
                    plate="B456DE02",
                    entered_at=self.starts_at + timedelta(minutes=1),
                )

    def test_normalized_plates_share_the_active_visit_index(self):
        Visit.objects.create(
            spot=self.spot,
            plate="a 123 bc 01",
            entered_at=self.starts_at,
        )
        self.assertEqual(Visit.objects.get().plate, "A123BC01")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Visit.objects.create(
                    spot=self.other_spot,
                    plate="А123ВС01",
                    entered_at=self.starts_at + timedelta(minutes=1),
                )

    def test_plate_is_globally_unique_across_drivers(self):
        other = self._driver("other@example.com")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Vehicle.objects.create(driver=other, plate="a-123-bc-01")

    def test_unknown_plate_visit_may_omit_the_driver(self):
        visit = Visit.objects.create(
            spot=self.spot,
            plate="ZZ999ZZ",
            entered_at=self.starts_at,
        )
        self.assertIsNone(visit.driver_id)
        self.assertIsNone(visit.booking_id)

    def test_visit_has_at_most_one_invoice(self):
        visit = Visit.objects.create(
            spot=self.spot,
            plate="A123BC01",
            entered_at=self.starts_at,
        )
        Invoice.objects.create(
            visit=visit,
            amount_kopecks=1500,
            issued_at=self.starts_at + timedelta(hours=1),
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Invoice.objects.create(
                    visit=visit,
                    amount_kopecks=2000,
                    issued_at=self.starts_at + timedelta(hours=1),
                )

    def test_login_email_is_unique_and_driver_is_one_user(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create_user(
                    username="second",
                    email="driver@example.com",
                    password="secret",
                )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Driver.objects.create(user=self.driver.user)

    def test_one_reminder_row_starts_unsent(self):
        booking = self._booking(
            spot=self.spot,
            start=self.starts_at,
            end=self.starts_at + timedelta(hours=1),
        )
        reminder = BookingReminder.objects.create(booking=booking)
        self.assertIsNone(reminder.sent_at)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                BookingReminder.objects.create(booking=booking)

    def test_initial_tariff_is_seeded(self):
        tariff = Tariff.objects.get()
        self.assertEqual(tariff.timezone, "Asia/Bishkek")
        self.assertEqual(tariff.day_starts_at, time(7, 0))
        self.assertEqual(tariff.night_starts_at, time(23, 0))
        self.assertEqual(tariff.day_rate_per_minute_kopecks, 200)
        self.assertEqual(tariff.night_rate_per_minute_kopecks, 100)


class PlateNormalizationTests(SimpleTestCase):
    def test_case_spaces_hyphens_and_cyrillic_lookalikes(self):
        self.assertEqual(normalize_plate("a 123 bc 01"), "A123BC01")
        self.assertEqual(normalize_plate("A-123-BC-01"), "A123BC01")
        self.assertEqual(normalize_plate("А123ВС01"), "A123BC01")
