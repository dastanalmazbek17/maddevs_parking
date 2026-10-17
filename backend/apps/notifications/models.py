"""Record that the single pre-end reminder for a booking was sent.

One row per booking. Sending the message is not implemented here.
"""

from django.db import models

from apps.bookings.models import Booking


class BookingReminder(models.Model):
    booking = models.OneToOneField(
        Booking,
        on_delete=models.CASCADE,
        related_name="reminder",
    )
    sent_at = models.DateTimeField()

    def __str__(self):
        return f"reminder for booking {self.booking_id}"
