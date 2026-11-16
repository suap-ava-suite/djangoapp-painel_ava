"""Contadores e histogramas; rótulos nunca contêm URLs ou dados de usuários."""

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest, multiprocess

BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 30, 60)
METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE", "CONNECT"}


def method_label(method):
    return method.upper() if method.upper() in METHODS else "OTHER"


class Metrics:
    def __init__(self):
        self.registry = CollectorRegistry()
        self.server_requests = Counter(
            "painel_http_server_requests_total",
            "Respostas produzidas pelo Django, incluindo redirecionamentos.",
            ("route", "method", "status"),
            registry=self.registry,
        )
        self.server_duration = Histogram(
            "painel_http_server_request_duration_seconds",
            "Duração do processamento Django até a criação da resposta, em segundos.",
            ("route", "method"),
            buckets=BUCKETS,
            registry=self.registry,
        )
        client_labels = ("dependency", "environment", "operation", "purpose", "method")
        self.client_requests = Counter(
            "painel_http_client_requests_total",
            "Tentativas HTTP externas; status none indica ausência de resposta HTTP.",
            (*client_labels, "status", "result"),
            registry=self.registry,
        )
        self.client_duration = Histogram(
            "painel_http_client_request_duration_seconds",
            "Duração de cada chamada HTTP externa observada pelo Django, em segundos.",
            client_labels,
            buckets=BUCKETS,
            registry=self.registry,
        )
        self.invalid_json = Counter(
            "painel_http_client_invalid_json_total",
            "Respostas externas cujo JSON não pôde ser interpretado.",
            ("dependency", "environment", "operation", "purpose"),
            registry=self.registry,
        )
        self.moodle_operations = Counter(
            "painel_moodle_operations_total",
            "Resultado final de uma operação Moodle, após as tentativas HTTP.",
            ("environment", "operation", "outcome"),
            registry=self.registry,
        )
        self.moodle_batches = Counter(
            "painel_moodle_batches_total",
            "Consultas agregadas aos Moodles: complete, partial, failure ou no_targets.",
            ("operation", "outcome"),
            registry=self.registry,
        )


METRICS = Metrics()


def exposition():
    import os

    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
    else:
        registry = METRICS.registry
    return generate_latest(registry)
