"""Periodic nudge so clocks, not only writes, refresh the map."""

from celery import shared_task

from apps.parking.realtime import notify_spots_changed as publish_spots_changed


@shared_task
def notify_spots_changed():
    publish_spots_changed()
