"""Database constraints for bookings and visits, checked through the ORM."""

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Driver
from apps.bookings.models import Booking, BookingStatus
from apps.parking.models import Spot
from apps.visits.models import Visit


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
        visit.amount_kopecks = 1500
        visit.save(update_fields=["exited_at", "amount_kopecks"])

        Visit.objects.create(
            spot=self.other_spot,
            plate="A123BC01",
            entered_at=self.starts_at + timedelta(minutes=31),
        )
