"""Public occupancy socket. It does not read the database."""

import json

from channels.generic.websocket import AsyncWebsocketConsumer

from apps.parking.realtime import SPOTS_GROUP


class SpotConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.channel_layer.group_add(SPOTS_GROUP, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(SPOTS_GROUP, self.channel_name)

    async def spots_changed(self, event):
        await self.send(text_data=json.dumps({"type": "spots.changed"}))
