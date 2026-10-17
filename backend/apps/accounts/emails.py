"""Login email stored in lowercase. Case-insensitive uniqueness is a database constraint."""


def normalize_email(value):
    if value is None:
        return value
    return str(value).strip().lower()
