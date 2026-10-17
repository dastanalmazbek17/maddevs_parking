from django.urls import path

from apps.visits.views import InvoiceListView, VisitListView

urlpatterns = [
    path("visits/", VisitListView.as_view()),
    path("invoices/", InvoiceListView.as_view()),
]
