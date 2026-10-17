from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import LoginSerializer, RegisterSerializer
from apps.accounts.services import login, register

_DUPLICATE_EMAIL = {
    "code": "validation_error",
    "detail": "Проверьте поля запроса.",
    "fields": {"email": "Пользователь с такой почтой уже есть."},
}
_INVALID_LOGIN = {
    "code": "invalid_credentials",
    "detail": "Неверная почта или пароль.",
}


class RegisterView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                user, token = register(**serializer.validated_data)
        except IntegrityError:
            return Response(_DUPLICATE_EMAIL, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"email": user.email, "token": token.key},
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = login(**serializer.validated_data)
        if result is None:
            return Response(_INVALID_LOGIN, status=status.HTTP_400_BAD_REQUEST)
        _user, token = result
        return Response({"token": token.key})


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"email": request.user.email})
