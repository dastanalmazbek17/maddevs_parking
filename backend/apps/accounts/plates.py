"""Canonical plate text stored in the database and used by unique indexes."""

from django.db import models

# Cyrillic letters that appear on Russian plates, folded to Latin lookalikes.
_LOOKALIKES = str.maketrans(
    {
        "А": "A",
        "В": "B",
        "Е": "E",
        "К": "K",
        "М": "M",
        "Н": "H",
        "О": "O",
        "Р": "P",
        "С": "C",
        "Т": "T",
        "У": "Y",
        "Х": "X",
    }
)
_SEPARATORS = set("-–—_")


def normalize_plate(value):
    """Uppercase, drop spaces and hyphens, fold Cyrillic lookalikes to Latin."""

    if value is None:
        return None
    folded = str(value).upper().translate(_LOOKALIKES)
    return "".join(ch for ch in folded if not ch.isspace() and ch not in _SEPARATORS)


class PlateField(models.CharField):
    """CharField that persists `normalize_plate` so indexes see one spelling."""

    def pre_save(self, model_instance, add):
        normalized = normalize_plate(getattr(model_instance, self.attname))
        setattr(model_instance, self.attname, normalized)
        return normalized

    def get_prep_value(self, value):
        return normalize_plate(super().get_prep_value(value))
