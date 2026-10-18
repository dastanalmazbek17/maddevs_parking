"""Tell every connected map that it should reload spot state.

The message carries no occupancy. The HTTP list stays the only source of truth.
"""

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

SPOTS_GROUP = "spots"


def notify_spots_changed():
    """Publish after the current transaction commits. Outside one, send now."""

    transaction.on_commit(_send_spots_changed)


def _send_spots_changed():
    layer = get_channel_layer()
    if layer is None:
        return
    async_to_sync(layer.group_send)(SPOTS_GROUP, {"type": "spots.changed"})
