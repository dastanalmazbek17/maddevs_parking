from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.accounts.urls")),
    path("api/", include("apps.parking.urls")),
    path("api/bookings/", include("apps.bookings.urls")),
    path("api/visits/", include("apps.visits.urls")),
    path("api/tariffs/", include("apps.tariffs.urls")),
    path("api/gate/", include("apps.gate.urls")),
]
