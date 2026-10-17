"""Create a driver account and sign in with an email and a DRF token."""

from django.contrib.auth import authenticate, get_user_model
from rest_framework.authtoken.models import Token

from apps.accounts.emails import normalize_email
from apps.accounts.models import Driver

User = get_user_model()


def register(email, password):
    user = User.objects.create_user(email=email, password=password)
    Driver.objects.create(user=user)
    token, _created = Token.objects.get_or_create(user=user)
    return user, token


def login(email, password):
    user = authenticate(email=normalize_email(email), password=password)
    if user is None:
        return None
    token, _created = Token.objects.get_or_create(user=user)
    return user, token
