"""Celery task that sends one reminder email per booking."""

import logging

from celery import shared_task

from apps.notifications.services import send_due_reminders as deliver_due_reminders

logger = logging.getLogger(__name__)


@shared_task
def send_due_reminders():
    sent = deliver_due_reminders()
    logger.info("Sent %s booking reminders", sent)
    return sent
