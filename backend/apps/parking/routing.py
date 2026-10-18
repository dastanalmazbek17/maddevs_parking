"""WebSocket routes for live occupancy."""

from django.urls import path

from apps.parking.consumers import SpotConsumer

websocket_urlpatterns = [
    path("ws/spots/", SpotConsumer.as_asgi()),
]
