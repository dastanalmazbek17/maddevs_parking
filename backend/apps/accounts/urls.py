from django.urls import path

from apps.accounts.views import (
    LoginView,
    MeView,
    RegisterView,
    VehicleDetailView,
    VehicleListView,
)

urlpatterns = [
    path("auth/register/", RegisterView.as_view()),
    path("auth/login/", LoginView.as_view()),
    path("me/", MeView.as_view()),
    path("vehicles/", VehicleListView.as_view()),
    path("vehicles/<int:pk>/", VehicleDetailView.as_view()),
]
