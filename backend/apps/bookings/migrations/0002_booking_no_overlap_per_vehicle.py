import apps.bookings.models
import django.contrib.postgres.constraints
import django.contrib.postgres.fields.ranges
import django.db.models.expressions
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0001_initial"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="booking",
            constraint=django.contrib.postgres.constraints.ExclusionConstraint(
                condition=models.Q(("status__in", ("active", "checked_in"))),
                expressions=[
                    ("vehicle", "="),
                    (
                        apps.bookings.models.TsTzRange(
                            django.db.models.expressions.F("starts_at"),
                            django.db.models.expressions.F("ends_at"),
                            django.contrib.postgres.fields.ranges.RangeBoundary(),
                        ),
                        "&&",
                    ),
                ],
                name="booking_no_overlap_per_vehicle",
            ),
        ),
    ]
