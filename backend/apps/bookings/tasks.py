"""Celery task that releases a booking when the driver does not arrive."""

import logging

from celery import shared_task

from apps.bookings.services import expire_overdue_bookings as release_overdue_bookings

logger = logging.getLogger(__name__)


@shared_task
def expire_overdue_bookings():
    released = release_overdue_bookings()
    logger.info("Expired %s overdue bookings", released)
    return released
