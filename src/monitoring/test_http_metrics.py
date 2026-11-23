import json
import os
import subprocess  # noqa: S404
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import requests
import responses
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import path

from monitoring import metrics
from monitoring.http import MoodleBatch, destination_for, install_requests_monitoring
from monitoring.middleware import HTTPMetricsMiddleware
from monitoring.views import metrics_view
from painel.middleware import ExceptionMiddleware
from painel.v1.services import get_json_api


def status_view(request, status):
    return HttpResponse(status=status)


urlpatterns = [path("items/<int:status>/", status_view), path("", lambda request: HttpResponse())]


@pytest.fixture(autouse=True)
def isolated_metrics(monkeypatch, settings):
    monkeypatch.setattr(metrics, "METRICS", metrics.Metrics())
    settings.ROOT_URLCONF = __name__
    settings.SUAP = {"BASE_URL": "https://suap.example.test"}
    settings.SUAP_AUTH = {"BASE_URL": "https://suap.example.test"}
    settings.PAINEL_METRICS_TOKEN = "scrape-test-token"  # noqa: S105
    install_requests_monitoring()
    return metrics.METRICS.registry


def sample(registry, name, **labels):
    return registry.get_sample_value(name, labels) or 0


def ambiente(name="A", pk=1):
    return SimpleNamespace(
        nome=name,
        pk=pk,
        token="private-moodle-token",
        moodle_base_api_url=f"https://moodle-{pk}.test/admin/tool/painelava/api",
    )


@pytest.mark.parametrize("status", [200, 204, 302, 400, 401, 403, 404, 422, 500, 503])
def test_server_final_status_and_normalized_route(isolated_metrics, status):
    request = RequestFactory().get(f"/items/{status}/?username=private")
    response = HTTPMetricsMiddleware(lambda request: HttpResponse(status=status))(request)
    assert response.status_code == status
    assert (
        sample(
            isolated_metrics,
            "painel_http_server_requests_total",
            route="items/<int:status>/",
            method="GET",
            status=str(status),
        )
        == 1
    )
    assert (
        sample(
            isolated_metrics,
            "painel_http_server_request_duration_seconds_count",
            route="items/<int:status>/",
            method="GET",
        )
        == 1
    )
    assert b"private" not in metrics.exposition()


def test_early_rejection_and_unmatched_routes(isolated_metrics):
    middleware = HTTPMetricsMiddleware(lambda request: HttpResponse(status=403))
    for url in ["/items/1/", "/unknown-private-path/", "/another-user/"]:
        middleware(RequestFactory().get(url))
    assert (
        sample(isolated_metrics, "painel_http_server_requests_total", route="unmatched", method="GET", status="403")
        == 2
    )
    assert b"unknown-private-path" not in metrics.exposition()


def test_exception_still_records_server_failure(isolated_metrics):
    def fail(request):
        raise RuntimeError("failure")

    with pytest.raises(RuntimeError):
        HTTPMetricsMiddleware(fail)(RequestFactory().get("/"))
    assert sample(isolated_metrics, "painel_http_server_requests_total", route="/", method="GET", status="500") == 1


@pytest.mark.parametrize("url", ["/static/a.js", "/media/a.png", "/health/", "/probes/readiness/"])
def test_background_endpoints_excluded(isolated_metrics, url):
    HTTPMetricsMiddleware(lambda request: HttpResponse())(RequestFactory().get(url))
    assert b"painel_http_server_requests_total{" not in metrics.exposition()


def test_scrape_bypasses_application_and_requires_token(settings, isolated_metrics):
    def application(request):
        raise AssertionError("Scrape must not access sessions or the database")

    middleware = HTTPMetricsMiddleware(application)
    factory = RequestFactory()
    assert middleware(factory.get("/metrics")).status_code == 403
    request = factory.get("/metrics", HTTP_AUTHORIZATION="Bearer scrape-test-token")
    response = middleware(request)
    assert response.status_code == 200
    assert "text/plain" in response["Content-Type"]
    assert response["Cache-Control"] == "no-store"
    assert metrics_view(factory.post("/metrics", HTTP_AUTHORIZATION="Bearer scrape-test-token")).status_code == 405
    settings.PAINEL_METRICS_TOKEN = ""
    assert middleware(request).status_code == 404
    assert b"scrape-test-token" not in metrics.exposition()


@pytest.mark.parametrize("status", [200, 302, 400, 401, 404, 500, 503])
def test_suap_http_status_and_latency(isolated_metrics, status):
    url = "https://suap.example.test/api/rh/eu/?username=private"
    with responses.RequestsMock() as mock:
        mock.get(url, status=status, json={})
        response = requests.get(url, allow_redirects=False, timeout=1)
    assert response.status_code == status
    labels = dict(dependency="suap", environment="suap", operation="/api/rh/eu/", purpose="application", method="GET")
    assert (
        sample(isolated_metrics, "painel_http_client_requests_total", **labels, status=str(status), result="response")
        == 1
    )
    assert sample(isolated_metrics, "painel_http_client_request_duration_seconds_count", **labels) == 1
    assert b"private" not in metrics.exposition()


@pytest.mark.parametrize(
    "error,result",
    [
        (requests.Timeout(), "timeout"),
        (requests.exceptions.SSLError(), "tls_error"),
        (requests.ConnectionError(), "connection_error"),
        (requests.RequestException(), "request_error"),
    ],
)
def test_transport_errors_have_no_http_status(isolated_metrics, error, result):
    url = "https://suap.example.test/o/token/"
    with responses.RequestsMock() as mock:
        mock.post(url, body=error)
        with pytest.raises(type(error)):
            requests.post(url, timeout=1)
    assert (
        sample(
            isolated_metrics,
            "painel_http_client_requests_total",
            dependency="suap",
            environment="suap",
            operation="/o/token/",
            purpose="application",
            method="POST",
            status="none",
            result=result,
        )
        == 1
    )


def test_oauth_private_session_and_invalid_json_counted_once(isolated_metrics):
    from django_suap_auth.client import SuapOAuth2Client

    client = SuapOAuth2Client(base_url="https://suap.example.test")
    with responses.RequestsMock() as mock:
        mock.post("https://suap.example.test/o/token/", json={"access_token": "private-token"})
        assert client.exchange_code_for_token("private-code")["access_token"] == "private-token"  # noqa: S105
        mock.get("https://suap.example.test/api/rh/eu/", body="not json")
        response = client._session.get("https://suap.example.test/api/rh/eu/", timeout=1)
        for _ in range(2):
            with pytest.raises(ValueError):
                response.json()
    assert (
        sample(
            isolated_metrics,
            "painel_http_client_requests_total",
            dependency="suap",
            environment="suap",
            operation="/o/token/",
            purpose="application",
            method="POST",
            status="200",
            result="response",
        )
        == 1
    )
    assert (
        sample(
            isolated_metrics,
            "painel_http_client_invalid_json_total",
            dependency="suap",
            environment="suap",
            operation="/api/rh/eu/",
            purpose="application",
        )
        == 1
    )
    assert b"private-token" not in metrics.exposition()


def test_idempotent_install_unknown_hosts_and_path_cardinality(settings, isolated_metrics):
    original = requests.sessions.Session.request
    install_requests_monitoring()
    assert requests.sessions.Session.request is original
    assert destination_for("https://suap.example.test.evil/api/rh/eu/") is None
    assert destination_for("https://unrelated.example.test/api/rh/eu/") is None
    assert destination_for("https://suap.example.test/private/12345/").operation == "other"
    settings.SUAP_AUTH["USER_INFO_ENDPOINTS"] = [{"endpoint": "/api/ensino/diarios/{semestre}/"}]
    assert (
        destination_for("https://suap.example.test/api/ensino/diarios/2026.2/").operation
        == "/api/ensino/diarios/{semestre}/"
    )
    with responses.RequestsMock() as mock:
        mock.get("https://unrelated.example.test/", json={})
        requests.get("https://unrelated.example.test/", timeout=1)
    assert b"painel_http_client_requests_total{" not in metrics.exposition()


def test_moodle_retry_is_two_attempts_and_one_operation(isolated_metrics):
    ava = ambiente()
    url = ava.moodle_base_api_url + "/?get_diarios&username=private"
    with responses.RequestsMock() as mock, patch("painel.v1.services.time.sleep"):
        mock.get(url, body=requests.ConnectionError())
        mock.get(url, json={"diarios": []})
        assert get_json_api(ava, "get_diarios", username="private") == {"diarios": []}
    labels = dict(dependency="moodle", environment="A", operation="get_diarios", purpose="application", method="GET")
    assert (
        sample(
            isolated_metrics, "painel_http_client_requests_total", **labels, status="none", result="connection_error"
        )
        == 1
    )
    assert sample(isolated_metrics, "painel_http_client_requests_total", **labels, status="200", result="response") == 1
    assert (
        sample(
            isolated_metrics,
            "painel_moodle_operations_total",
            environment="A",
            operation="get_diarios",
            outcome="success",
        )
        == 1
    )


@pytest.mark.parametrize(
    "body,status,outcome",
    [
        ("not json", 200, "invalid_response"),
        ('{"error":{"message":"Usuário não encontrado."}}', 404, "expected_absence"),
        ('{"error":{"message":"Serviço não existe"}}', 404, "failure"),
        ("{}", 500, "failure"),
    ],
)
def test_moodle_logical_outcome(isolated_metrics, body, status, outcome):
    ava = ambiente()
    with responses.RequestsMock() as mock, patch("painel.v1.services._registrar_falha_moodle"):
        mock.get(ava.moodle_base_api_url + "/?get_diarios&", body=body, status=status)
        assert get_json_api(ava, "get_diarios") is None
    assert (
        sample(
            isolated_metrics,
            "painel_moodle_operations_total",
            environment="A",
            operation="get_diarios",
            outcome=outcome,
        )
        == 1
    )
    if body == "not json":
        assert (
            sample(
                isolated_metrics,
                "painel_http_client_invalid_json_total",
                dependency="moodle",
                environment="A",
                operation="get_diarios",
                purpose="application",
            )
            == 1
        )


@pytest.mark.parametrize(
    "statuses,outcome",
    [
        ([], "no_targets"),
        ([200, 200], "complete"),
        ([200, 503], "partial"),
        ([503, 503], "failure"),
        ([200, 404], "complete"),
    ],
)
def test_batches_track_expected_absence_and_partial_results(isolated_metrics, statuses, outcome):
    from concurrent.futures import ThreadPoolExecutor

    ambientes = [ambiente(str(i), i) for i in range(len(statuses))]
    batch = MoodleBatch(ambientes)

    def call(ava):
        with batch.track(ava):
            return get_json_api(ava, "get_diarios")

    with responses.RequestsMock() as mock, patch("painel.v1.services._registrar_falha_moodle"):
        for ava, status in zip(ambientes, statuses):
            mock.get(
                ava.moodle_base_api_url + "/?get_diarios&",
                status=status,
                json={"error": {"message": "Usuário não encontrado."}} if status == 404 else {},
            )
        with ThreadPoolExecutor(max_workers=3) as executor:
            list(executor.map(call, ambientes))
    batch.observe("get_diarios")
    assert sample(isolated_metrics, "painel_moodle_batches_total", operation="get_diarios", outcome=outcome) == 1


def test_probe_purpose_and_readiness_status(settings, isolated_metrics):
    from health.views import readiness

    settings.DEBUG = False
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    url = "https://suap.example.test/comum/solicitar_trocar_senha/"
    with responses.RequestsMock() as mock, patch("health.views.connection"):
        mock.get(url, status=200)
        response = readiness(RequestFactory().get("/probes/readiness/"))
        assert response.status_code == 200
        assert json.loads(response.content)["ALL"] is True
        mock.replace(responses.GET, url, status=503)
        assert readiness(RequestFactory().get("/probes/readiness/")).status_code == 503
    assert (
        sample(
            isolated_metrics,
            "painel_http_client_requests_total",
            dependency="suap",
            environment="suap",
            operation="readiness",
            purpose="probe",
            method="GET",
            status="200",
            result="response",
        )
        == 1
    )


@pytest.mark.parametrize("error", ["psycopg", "pool"])
def test_database_errors_return_http_500(error):
    import psycopg
    import psycopg_pool

    def fail(request):
        raise (psycopg.OperationalError() if error == "psycopg" else psycopg_pool.PoolTimeout())

    assert ExceptionMiddleware(fail)(RequestFactory().get("/")).status_code == 500


def test_multiprocess_aggregates_workers(tmp_path):
    env = {**os.environ, "PROMETHEUS_MULTIPROC_DIR": str(tmp_path)}
    worker = (
        "from monitoring.metrics import METRICS; import sys; "
        "METRICS.server_requests.labels(route='/',method='GET',status='200').inc(int(sys.argv[1]))"
    )
    for count in [2, 3]:
        subprocess.run(  # noqa: S603
            [sys.executable, "-c", worker, str(count)], env=env, check=True, capture_output=True
        )
    output = subprocess.run(
        [sys.executable, "-c", "from monitoring.metrics import exposition; print(exposition().decode())"],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    ).stdout  # noqa: S603
    assert 'painel_http_server_requests_total{method="GET",route="/",status="200"} 5.0' in output


@pytest.mark.django_db
@pytest.mark.parametrize("operation", ["get_diarios", "get_progresso"])
def test_real_aggregate_records_partial_result(isolated_metrics, settings, operation):
    import re

    from painel.models import Ambiente
    from painel.v1 import services

    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    ambientes = [
        Ambiente.objects.create(nome=f"metrics-{i}", url=f"https://metrics-{i}.test", token="test", cor_mestra="#000")
        for i in range(2)
    ]
    body = {"diarios": []} if operation == "get_diarios" else []
    with (
        responses.RequestsMock() as mock,
        patch.object(Ambiente, "cached", return_value=ambientes),
        patch("painel.v1.services._registrar_falha_moodle"),
    ):
        mock.get(re.compile(re.escape(ambientes[0].moodle_base_api_url) + r"/\?.*"), json=body)
        mock.get(re.compile(re.escape(ambientes[1].moodle_base_api_url) + r"/\?.*"), status=503, json={})
        result = getattr(services, operation)("metrics-user")
    assert isinstance(result, dict)
    assert sample(isolated_metrics, "painel_moodle_batches_total", operation=operation, outcome="partial") == 1


@pytest.mark.django_db
@pytest.mark.parametrize("version", ["v1", "v2"])
@pytest.mark.parametrize("status", [200, 401])
def test_authentication_endpoints_measure_suap_and_server(settings, isolated_metrics, client, version, status):
    settings.ROOT_URLCONF = "urls"
    endpoint = "/api/v1/authenticate/" if version == "v1" else "/api/v2/token/pair/"
    with responses.RequestsMock() as mock:
        mock.post("https://suap.example.test/api/token/pair", status=status, json={"access": "test-access"})
        if status == 200:
            # O primeiro endpoint de perfil não atende o vínculo deste usuário; o segundo atende.
            mock.get("https://suap.example.test/api/rh/meus-dados/", status=404, json={})
            mock.get(
                "https://suap.example.test/api/ensino/meus-dados-aluno/",
                json={"matricula": "metrics-login", "nome": "Aluno Teste", "email": "aluno@example.test"},
            )
        response = client.post(
            endpoint,
            data=json.dumps({"username": "metrics-login", "password": "test-password"}),
            content_type="application/json",
        )
    assert response.status_code == status
    assert (
        sample(
            isolated_metrics,
            "painel_http_server_requests_total",
            route=endpoint.lstrip("/"),
            method="POST",
            status=str(status),
        )
        == 1
    )
    assert (
        sample(
            isolated_metrics,
            "painel_http_client_requests_total",
            dependency="suap",
            environment="suap",
            operation="/api/token/pair",
            purpose="application",
            method="POST",
            status=str(status),
            result="response",
        )
        == 1
    )
    if status == 200:
        assert (
            sample(
                isolated_metrics,
                "painel_http_client_requests_total",
                dependency="suap",
                environment="suap",
                operation="/api/rh/meus-dados/",
                purpose="application",
                method="GET",
                status="404",
                result="response",
            )
            == 1
        )
        assert (
            sample(
                isolated_metrics,
                "painel_http_client_requests_total",
                dependency="suap",
                environment="suap",
                operation="/api/ensino/meus-dados-aluno/",
                purpose="application",
                method="GET",
                status="200",
                result="response",
            )
            == 1
        )
    assert b"metrics-login" not in metrics.exposition()
    assert b"test-password" not in metrics.exposition()
