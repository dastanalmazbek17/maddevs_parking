from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.gate.serializers import PlateSerializer
from apps.parking.presenters import invoice_payload, isoformat_utc, visit_payload
from apps.visits.services import enter, exit_visit


class GateEnterView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PlateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        visit = enter(serializer.validated_data["plate"])
        return Response(visit_payload(visit), status=status.HTTP_201_CREATED)


class GateExitView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PlateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        visit, invoice = exit_visit(serializer.validated_data["plate"])
        payload = visit_payload(visit)
        payload["exited_at"] = isoformat_utc(visit.exited_at)
        return Response({"visit": payload, "invoice": invoice_payload(invoice)})
