from django.urls import path

from apps.gate.views import GateEnterView, GateExitView

urlpatterns = [
    path("enter/", GateEnterView.as_view()),
    path("exit/", GateExitView.as_view()),
]
