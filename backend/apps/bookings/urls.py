from django.urls import path

from apps.bookings.views import BookingCancelView, BookingListCreateView

urlpatterns = [
    path("bookings/", BookingListCreateView.as_view()),
    path("bookings/<int:pk>/cancel/", BookingCancelView.as_view()),
]
