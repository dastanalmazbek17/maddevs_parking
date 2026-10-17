from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.accounts.models import Driver
from apps.parking.presenters import invoice_payload, isoformat_utc, visit_payload
from apps.visits.models import Invoice, Visit


class HistoryPagination(PageNumberPagination):
    page_size = 20


def _driver(user):
    return get_object_or_404(Driver, user=user)


def _owned(driver):
    plates = driver.vehicles.values("plate")
    return Q(driver=driver) | Q(plate__in=plates)


def _history_payload(visit):
    payload = visit_payload(visit)
    payload["exited_at"] = isoformat_utc(visit.exited_at)
    try:
        invoice = visit.invoice
    except Invoice.DoesNotExist:
        payload["invoice"] = None
    else:
        payload["invoice"] = invoice_payload(invoice)
    return payload


class VisitListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        driver = _driver(request.user)
        visits = (
            Visit.objects.filter(_owned(driver))
            .select_related("spot", "invoice")
            .order_by("-entered_at", "-pk")
        )
        paginator = HistoryPagination()
        page = paginator.paginate_queryset(visits, request, view=self)
        return paginator.get_paginated_response([_history_payload(visit) for visit in page])


class InvoiceListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        driver = _driver(request.user)
        invoices = (
            Invoice.objects.filter(Q(visit__driver=driver) | Q(visit__plate__in=driver.vehicles.values("plate")))
            .order_by("-issued_at", "-pk")
        )
        paginator = HistoryPagination()
        page = paginator.paginate_queryset(invoices, request, view=self)
        return paginator.get_paginated_response(
            [
                {
                    "id": invoice.pk,
                    "visit_id": invoice.visit_id,
                    **invoice_payload(invoice),
                }
                for invoice in page
            ]
        )
