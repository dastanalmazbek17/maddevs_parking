import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_driver_user_global_plate"),
        ("bookings", "0002_alter_booking_plate_alter_booking_status_and_more"),
        ("parking", "0001_initial"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="booking",
            name="booking_plate_not_blank",
        ),
        migrations.RemoveField(
            model_name="booking",
            name="plate",
        ),
        migrations.RemoveField(
            model_name="booking",
            name="driver",
        ),
        migrations.AddField(
            model_name="booking",
            name="vehicle",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="bookings",
                to="accounts.vehicle",
            ),
        ),
        migrations.AlterField(
            model_name="booking",
            name="vehicle",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="bookings",
                to="accounts.vehicle",
            ),
        ),
        migrations.AlterField(
            model_name="booking",
            name="status",
            field=models.CharField(
                choices=[
                    ("active", "Active"),
                    ("checked_in", "Checked in"),
                    ("completed", "Completed"),
                    ("cancelled", "Cancelled"),
                    ("expired", "Expired"),
                ],
                default="active",
                max_length=16,
            ),
        ),
    ]
