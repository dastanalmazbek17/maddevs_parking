"""Public spot socket. It carries a signal and no occupancy."""

import pytest
from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator

from config.asgi import application


def _run(scenario):
    async_to_sync(scenario)()


async def _open(origin=None):
    headers = []
    if origin is not None:
        headers.append((b"origin", origin.encode("latin1")))
    communicator = WebsocketCommunicator(application, "/ws/spots/", headers=headers)
    connected, _close_code = await communicator.connect()
    return communicator, connected


@pytest.mark.django_db
def test_socket_accepts_a_public_client_and_rejects_a_foreign_origin():
    async def scenario():
        allowed, connected = await _open("http://localhost")
        assert connected
        await allowed.disconnect()
        denied, connected = await _open("http://evil.example")
        assert not connected
        await denied.disconnect()

    _run(scenario)
