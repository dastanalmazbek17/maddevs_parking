"""One reminder row per booking.

`sent_at` stays null until the sender claims the row with
`UPDATE ... SET sent_at = now() WHERE booking_id = ? AND sent_at IS NULL`.
Sending itself is not implemented here.
"""

from django.db import models

from apps.bookings.models import Booking


class BookingReminder(models.Model):
    booking = models.OneToOneField(
        Booking,
        on_delete=models.CASCADE,
        related_name="reminder",
    )
    sent_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"reminder for booking {self.booking_id}"
