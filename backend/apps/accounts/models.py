"""Login account and the plates registered to that driver."""

from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from apps.accounts.emails import normalize_email
from apps.accounts.plates import PlateField


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("An email is required.")
        user = self.model(email=normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Login is the email address. There is no username."""

    username = None
    email = models.EmailField(unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("email"), name="user_email_ci_unique"),
        ]

    def save(self, *args, **kwargs):
        self.email = normalize_email(self.email)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email


class Driver(models.Model):
    """Profile for the login account."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="driver",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.email


class Vehicle(models.Model):
    """One normalized plate. The same plate cannot belong to two drivers."""

    driver = models.ForeignKey(
        Driver,
        on_delete=models.CASCADE,
        related_name="vehicles",
    )
    plate = PlateField(max_length=32, unique=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=~Q(plate=""),
                name="vehicle_plate_not_blank",
            ),
        ]

    def __str__(self):
        return self.plate
