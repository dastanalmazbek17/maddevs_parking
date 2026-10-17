"""Database constraints for bookings and visits, checked through the ORM."""

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.accounts.models import Driver
from apps.accounts.plates import normalize_plate
from apps.bookings.models import Booking, BookingStatus
from apps.parking.models import Spot
from apps.visits.models import Invoice, Visit


class DatabaseConstraintTests(TestCase):
    def setUp(self):
        self.spot = Spot.objects.create(code="A1")
        self.other_spot = Spot.objects.create(code="A2")
        self.driver = Driver.objects.create(email="driver@example.com")
        self.starts_at = timezone.now().replace(microsecond=0)

    def test_active_bookings_for_one_spot_cannot_overlap(self):
        Booking.objects.create(
            spot=self.spot,
            driver=self.driver,
            plate="A123BC01",
            starts_at=self.starts_at,
            ends_at=self.starts_at + timedelta(hours=2),
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Booking.objects.create(
                    spot=self.spot,
                    driver=self.driver,
                    plate="A123BC01",
                    starts_at=self.starts_at + timedelta(hours=1),
                    ends_at=self.starts_at + timedelta(hours=3),
                )

        Booking.objects.create(
            spot=self.spot,
            driver=self.driver,
            plate="A123BC01",
            starts_at=self.starts_at,
            ends_at=self.starts_at + timedelta(hours=2),
            status=BookingStatus.CANCELLED,
        )
        Booking.objects.create(
            spot=self.spot,
            driver=self.driver,
            plate="A123BC01",
            starts_at=self.starts_at,
            ends_at=self.starts_at + timedelta(hours=2),
            status=BookingStatus.EXPIRED,
        )
        Booking.objects.create(
            spot=self.spot,
            driver=self.driver,
            plate="A123BC01",
            starts_at=self.starts_at + timedelta(hours=2),
            ends_at=self.starts_at + timedelta(hours=3),
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

    def test_booking_end_must_be_after_start(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Booking.objects.create(
                    spot=self.spot,
                    driver=self.driver,
                    plate="A123BC01",
                    starts_at=self.starts_at,
                    ends_at=self.starts_at,
                )

    def test_visit_has_at_most_one_invoice(self):
        visit = Visit.objects.create(
            spot=self.spot,
            plate="A123BC01",
            entered_at=self.starts_at,
        )
        self.assertIsNone(visit.booking_id)
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


class PlateNormalizationTests(SimpleTestCase):
    def test_case_spaces_hyphens_and_cyrillic_lookalikes(self):
        self.assertEqual(normalize_plate("a 123 bc 01"), "A123BC01")
        self.assertEqual(normalize_plate("A-123-BC-01"), "A123BC01")
        self.assertEqual(normalize_plate("А123ВС01"), "A123BC01")
