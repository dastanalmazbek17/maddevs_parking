"""Registration and email login."""

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient

User = get_user_model()


class EmailUniquenessTests(TestCase):
    def test_case_variants_are_one_email(self):
        User.objects.create_user(email="A@x.com", password="secret-pass")
        self.assertEqual(User.objects.get().email, "a@x.com")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create_user(email="a@x.COM", password="secret-pass")


class RegisterAndLoginTests(TestCase):
    def test_register_and_login_with_a_different_case(self):
        client = APIClient()
        registered = client.post(
            "/api/auth/register/",
            {"email": "A@x.com", "password": "secret-pass"},
            format="json",
        )
        self.assertEqual(registered.status_code, 201)
        self.assertEqual(registered.data["email"], "a@x.com")
        token = registered.data["token"]

        logged_in = client.post(
            "/api/auth/login/",
            {"email": "a@x.COM", "password": "secret-pass"},
            format="json",
        )
        self.assertEqual(logged_in.status_code, 200)
        self.assertEqual(logged_in.data["token"], token)

        client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        me = client.get("/api/me/")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.data["email"], "a@x.com")
