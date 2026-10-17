"""JSON that keeps Cyrillic readable in curl output."""

from rest_framework.renderers import JSONRenderer


class UnicodeJSONRenderer(JSONRenderer):
    ensure_ascii = False
