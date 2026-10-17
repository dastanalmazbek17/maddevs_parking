from django.urls import path

from apps.parking.views import HealthView, SpotListView

urlpatterns = [
    path("health/", HealthView.as_view()),
    path("spots/", SpotListView.as_view()),
]
