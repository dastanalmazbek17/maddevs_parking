"""Tests use an in-memory channel layer so they do not need Redis."""

import pytest


@pytest.fixture(autouse=True)
def in_memory_channel_layer(settings):
    from channels import layers

    settings.CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
    }
    layers.channel_layers.backends = {}
    yield
    layers.channel_layers.backends = {}
