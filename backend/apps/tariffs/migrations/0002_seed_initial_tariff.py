from datetime import datetime, time, timezone

from django.db import migrations


def seed_initial_tariff(apps, schema_editor):
    Tariff = apps.get_model("tariffs", "Tariff")
    Tariff.objects.create(
        effective_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
        timezone="Asia/Bishkek",
        day_starts_at=time(7, 0),
        night_starts_at=time(23, 0),
        day_rate_per_minute_kopecks=200,
        night_rate_per_minute_kopecks=100,
    )


def remove_initial_tariff(apps, schema_editor):
    Tariff = apps.get_model("tariffs", "Tariff")
    Tariff.objects.filter(
        effective_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("tariffs", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_initial_tariff, remove_initial_tariff),
    ]
