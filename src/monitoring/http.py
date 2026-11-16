"""Instrumenta requests, inclusive as sessões privadas de django_suap_auth.

Uma observação por Session.request (resposta final após redirects). Novas tentativas
explícitas da aplicação são observadas individualmente. O transporte não é alterado.
"""

import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from threading import Lock
from time import perf_counter
from urllib.parse import urlsplit

import requests
from django.conf import settings

from . import metrics

_DESTINATION = ContextVar("painel_http_destination", default=None)
_BATCH = ContextVar("painel_moodle_batch", default=None)
SUAP_PATHS = {
    "/o/token/",
    "/api/token/pair",
    "/api/token/refresh",
    "/api/token/verify",
    "/api/rh/meus-dados/",
    "/api/ensino/meus-dados-aluno/",
    "/api/v2/minhas-informacoes/meus-dados/",
    "/api/rh/eu/",
    "/api/rh/meus-vinculos/",
    "/comum/solicitar_trocar_senha/",
}
MOODLE_OPERATIONS = {
    "get_diarios",
    "get_progresso",
    "get_course_info",
    "get_atualizacoes_counts",
    "get_diagnostico_usuario",
    "set_favourite_course",
    "set_visible_course",
    "set_user_preference",
    "enrol_course",
    "suspend_enrol",
    "sync_down_grades",
    "sync_up_enrolments",
}


@dataclass(frozen=True)
class Destination:
    dependency: str
    environment: str
    operation: str
    purpose: str = "application"
    base_url: str = ""

    def labels(self):
        return dict(
            dependency=self.dependency, environment=self.environment, operation=self.operation, purpose=self.purpose
        )


def _matches_base(url, base):
    target, configured = urlsplit(url), urlsplit(base)
    prefix = configured.path.rstrip("/")
    return (
        target.scheme == configured.scheme
        and target.netloc == configured.netloc
        and (target.path == prefix or target.path.startswith(prefix + "/"))
    )


def destination_for(url):
    explicit = _DESTINATION.get()
    if explicit and _matches_base(url, explicit.base_url):
        return explicit
    suap_auth = getattr(settings, "SUAP_AUTH", {})
    bases = [suap_auth.get("BASE_URL", ""), getattr(settings, "SUAP", {}).get("BASE_URL", "")]
    base = next((base for base in bases if base and _matches_base(url, base)), None)
    if not base:
        return None
    path = urlsplit(url).path
    paths = set(SUAP_PATHS)
    for endpoint in suap_auth.get("USER_INFO_ENDPOINTS", []):
        paths.add(endpoint if isinstance(endpoint, str) else endpoint["endpoint"])
    for template in sorted(paths):
        template_path = urlsplit(template).path
        pattern = re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(template_path))
        if re.fullmatch(pattern.rstrip("/"), path.rstrip("/")):
            return Destination("suap", "suap", template_path)
    return Destination("suap", "suap", "other")


@contextmanager
def destination_context(destination):
    token = _DESTINATION.set(destination)
    try:
        yield
    finally:
        _DESTINATION.reset(token)


def observe_invalid_json(destination):
    metrics.METRICS.invalid_json.labels(**destination.labels()).inc()


def _observe_json(response, destination):
    original = response.json
    recorded = False

    @wraps(original)
    def json(*args, **kwargs):
        nonlocal recorded
        try:
            return original(*args, **kwargs)
        except ValueError:
            if not recorded:
                observe_invalid_json(destination)
                recorded = True
            raise

    response.json = json


def install_requests_monitoring():
    original = requests.sessions.Session.request
    if getattr(original, "_painel_metrics", False):
        return

    @wraps(original)
    def request(session, method, url, *args, **kwargs):
        destination = destination_for(url)
        if destination is None:
            return original(session, method, url, *args, **kwargs)
        labels = {**destination.labels(), "method": metrics.method_label(method)}
        start = perf_counter()
        status, result = "none", "request_error"
        try:
            response = original(session, method, url, *args, **kwargs)
            status, result = str(response.status_code), "response"
            _observe_json(response, destination)
            return response
        except requests.exceptions.Timeout:
            result = "timeout"
            raise
        except requests.exceptions.SSLError:
            result = "tls_error"
            raise
        except requests.exceptions.ConnectionError:
            result = "connection_error"
            raise
        finally:
            metrics.METRICS.client_requests.labels(**labels, status=status, result=result).inc()
            metrics.METRICS.client_duration.labels(**labels).observe(perf_counter() - start)

    request._painel_metrics = True
    requests.sessions.Session.request = request


@dataclass
class MoodleOperation:
    outcome: str = "success"


@contextmanager
def moodle_operation(ambiente, operation):
    name = operation if operation in MOODLE_OPERATIONS else "other"
    destination = Destination("moodle", ambiente.nome, name, base_url=ambiente.moodle_base_api_url)
    observation = MoodleOperation()
    try:
        with destination_context(destination):
            yield observation
    except Exception:
        observation.outcome = "failure"
        raise
    finally:
        metrics.METRICS.moodle_operations.labels(
            environment=destination.environment, operation=name, outcome=observation.outcome
        ).inc()
        batch = _BATCH.get()
        if batch is not None and observation.outcome not in {"success", "expected_absence"}:
            batch.fail(ambiente)


class MoodleBatch:
    """Compartilha somente o resultado da consulta entre as threads, sem acessar o ORM."""

    def __init__(self, ambientes):
        self.failed = {ambiente.pk: False for ambiente in ambientes}
        self.lock = Lock()

    @contextmanager
    def track(self, ambiente):
        token = _BATCH.set(self)
        try:
            yield
        except Exception:
            self.fail(ambiente)
            raise
        finally:
            _BATCH.reset(token)

    def fail(self, ambiente):
        with self.lock:
            self.failed[ambiente.pk] = True

    def observe(self, operation):
        failures = sum(self.failed.values())
        if not self.failed:
            outcome = "no_targets"
        elif failures == len(self.failed):
            outcome = "failure"
        elif failures:
            outcome = "partial"
        else:
            outcome = "complete"
        metrics.METRICS.moodle_batches.labels(operation=operation, outcome=outcome).inc()
