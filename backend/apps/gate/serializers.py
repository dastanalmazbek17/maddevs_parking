from rest_framework import serializers


class PlateSerializer(serializers.Serializer):
    plate = serializers.CharField(allow_blank=True)
