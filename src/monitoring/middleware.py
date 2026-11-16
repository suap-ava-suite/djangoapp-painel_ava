from time import perf_counter

from django.urls import Resolver404, resolve

from . import metrics
from .views import metrics_view


class HTTPMetricsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Coleta interna sem sessão, acesso ao banco ou redirecionamento para login/HTTPS.
        if request.path_info in {"/metrics", "/metrics/"}:
            return metrics_view(request)
        if request.path_info.startswith(("/static/", "/media/", "/health/", "/probes/")):
            return self.get_response(request)
        start = perf_counter()
        status = "500"
        try:
            response = self.get_response(request)
            status = str(response.status_code)
            return response
        finally:
            match = getattr(request, "resolver_match", None)
            if match is None:
                try:
                    match = resolve(request.path_info)
                except Resolver404:
                    pass
            route = getattr(match, "route", None) or "unmatched"
            # A rota da raiz é a string vazia; preserva sua identidade.
            if match is not None and match.route == "":
                route = "/"
            method = metrics.method_label(request.method)
            metrics.METRICS.server_requests.labels(route=route, method=method, status=status).inc()
            metrics.METRICS.server_duration.labels(route=route, method=method).observe(perf_counter() - start)
