from django.conf import settings
from django.http import HttpResponse
from django.utils.crypto import constant_time_compare
from prometheus_client import CONTENT_TYPE_LATEST

from .metrics import exposition


def metrics_view(request):
    token = getattr(settings, "PAINEL_METRICS_TOKEN", "")
    if not token:
        return HttpResponse(status=404)
    if not constant_time_compare(request.headers.get("Authorization", ""), f"Bearer {token}"):
        return HttpResponse(status=403)
    if request.method != "GET":
        return HttpResponse(status=405, headers={"Allow": "GET"})
    return HttpResponse(exposition(), content_type=CONTENT_TYPE_LATEST, headers={"Cache-Control": "no-store"})
