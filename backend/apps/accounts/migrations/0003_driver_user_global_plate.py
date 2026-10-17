import apps.accounts.plates
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_alter_vehicle_plate_vehicle_vehicle_plate_not_blank"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="vehicle",
            name="vehicle_plate_per_driver",
        ),
        migrations.AlterField(
            model_name="vehicle",
            name="plate",
            field=apps.accounts.plates.PlateField(max_length=32, unique=True),
        ),
        migrations.AddField(
            model_name="driver",
            name="user",
            field=models.OneToOneField(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="driver",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RemoveField(
            model_name="driver",
            name="email",
        ),
        migrations.AlterField(
            model_name="driver",
            name="user",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="driver",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunSQL(
            sql=(
                "CREATE UNIQUE INDEX auth_user_email_not_blank_uniq "
                "ON auth_user (email) WHERE email <> ''"
            ),
            reverse_sql="DROP INDEX IF EXISTS auth_user_email_not_blank_uniq",
        ),
    ]
