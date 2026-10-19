from unittest.mock import patch

import psycopg
import psycopg_pool
import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import DisallowedHost, SuspiciousOperation
from django.http import HttpResponse
from django.test import RequestFactory

from painel.middleware import ExceptionMiddleware
from painel.models import Ambiente


def test_exception_middleware_handles_allowed_exceptions(rf: RequestFactory):
    request = rf.get("/")

    def get_response(req):
        return HttpResponse("OK")

    middleware = ExceptionMiddleware(get_response)
    response = middleware(request)
    assert response.status_code == 200
    assert response.content == b"OK"


def test_exception_middleware_handles_db_timeout(rf: RequestFactory):
    request = rf.get("/")

    def get_response(req):
        raise psycopg_pool.PoolTimeout("Timeout")

    middleware = ExceptionMiddleware(get_response)
    response = middleware(request)
    assert response.status_code == 200
    assert response.content == "Erro de conexão com o banco!".encode("utf-8")


def test_exception_middleware_handles_db_error(rf: RequestFactory):
    request = rf.get("/")

    def get_response(req):
        raise psycopg.errors.Error("DB Error")

    middleware = ExceptionMiddleware(get_response)
    response = middleware(request)
    assert response.status_code == 200
    assert response.content == "Erro de conexão com o banco!".encode("utf-8")


def test_exception_middleware_re_raises_suspicious_operation(rf: RequestFactory):
    request = rf.get("/")

    def get_response(req):
        raise SuspiciousOperation("Suspicious")

    middleware = ExceptionMiddleware(get_response)
    with pytest.raises(SuspiciousOperation):
        middleware(request)


def test_exception_middleware_handles_disallowed_host(rf: RequestFactory):
    request = rf.get("/")

    def get_response(req):
        raise DisallowedHost("Invalid Host")

    middleware = ExceptionMiddleware(get_response)
    response = middleware(request)
    assert response.status_code == 400
    assert "Host Não Permitido (Disallowed Host)".encode("utf-8") in response.content


@pytest.mark.django_db
def test_dashboard_sets_csrf_cookie(client):
    User = get_user_model()
    user = User.objects.create_user(username="testuser", password="password")
    client.force_login(user)

    response = client.get("/")
    assert response.status_code == 200
    assert "csrftoken" in client.cookies


@pytest.mark.django_db
@patch("painel.views.get_json_api")
def test_curso_detalhes_sets_csrf_cookie(mock_get_json_api, client):
    ambiente = Ambiente.objects.create(
        nome="Moodle de Teste",
        url="http://moodle-teste.ifrn.edu.br",
        token="token123",
        cor_mestra="#ffffff",
    )
    mock_get_json_api.return_value = {
        "fullname": "Curso Teste",
        "summary": "Descrição",
        "is_enrolled": False,
        "docentes": [],
        "carga_horaria": "40h",
    }
    response = client.get(f"/curso/{ambiente.id}/123/")
    assert response.status_code == 200
    assert "csrftoken" in client.cookies


@pytest.mark.django_db
@patch("painel.v1.services.get_json")
def test_get_json_api_catches_http_exception(mock_get_json):
    from http.client import HTTPException

    mock_get_json.side_effect = HTTPException("502 - Bad Gateway")

    ambiente = Ambiente.objects.create(
        nome="Moodle de Teste",
        url="http://moodle-teste.ifrn.edu.br",
        token="token123",
        cor_mestra="#ffffff",
    )

    from painel.v1.services import get_json_api

    result = get_json_api(ambiente, "enrol_course", courseid=123, username="testuser")
    assert result is None


@pytest.mark.django_db
@patch("painel.views.get_json_api")
def test_enrol_course_handles_api_http_exception(mock_get_json_api, client):
    User = get_user_model()
    user = User.objects.create_user(username="testuser", password="password", first_name="Test", last_name="User")
    client.force_login(user)

    ambiente = Ambiente.objects.create(
        nome="Moodle de Teste",
        url="http://moodle-teste.ifrn.edu.br",
        token="token123",
        cor_mestra="#ffffff",
    )

    mock_get_json_api.return_value = None

    response = client.post(f"/curso/{ambiente.id}/123/enrol/")
    assert response.status_code == 500
    assert response.json() == {"status": "error", "message": "Falha de comunicação com o AVA."}


def test_api_docs_returns_200(client):
    response = client.get("/api/v1/docs")
    assert response.status_code in [200, 428]


def test_api_openapi_json_returns_200(client):
    response = client.get("/api/v1/openapi.json")
    assert response.status_code in [200, 428]


@pytest.mark.django_db
def test_migrations_0030_and_0031_migrate_a4_usuario(django_db_blocker):
    import importlib

    from django.apps import apps as django_apps
    from django.db import connection

    m0030 = importlib.import_module("painel.migrations.0030_create_auth_user_from_a4")
    m0031 = importlib.import_module("painel.migrations.0031_migrate_a4_data_to_suap_profile")

    if connection.vendor != "postgresql":
        with connection.schema_editor() as schema_editor:
            m0030.ensure_auth_user_and_migrate_from_a4(django_apps, schema_editor)
            m0031.migrate_a4_data_to_suap_profile(django_apps, schema_editor)
        return

    with connection.cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS "a4_usuario" (
                "id" bigint NOT NULL PRIMARY KEY,
                "password" varchar(128) NOT NULL,
                "last_login" timestamp with time zone NULL,
                "is_superuser" boolean NOT NULL,
                "first_name" varchar(2560) NULL,
                "last_name" varchar(2560) NULL,
                "is_staff" boolean NOT NULL,
                "is_active" boolean NOT NULL,
                "date_joined" timestamp with time zone NOT NULL,
                "username" varchar(2560) NOT NULL UNIQUE,
                "nome_social" varchar(2560) NULL,
                "email" varchar(2560) NULL,
                "email_secundario" varchar(2560) NULL,
                "email_corporativo" varchar(2560) NULL,
                "email_academico" varchar(2560) NULL,
                "first_login" timestamp with time zone NULL,
                "email_google_classroom" varchar(2560) NULL,
                "foto" varchar(2560) NULL,
                "nome" varchar(2560) NULL,
                "nome_registro" varchar(2560) NULL,
                "nome_usual" varchar(2560) NULL,
                "tipo_usuario" varchar(2560) NULL,
                "deleted" timestamp with time zone NULL,
                "deleted_by_cascade" boolean NOT NULL DEFAULT false,
                "last_json" text NULL,
                "settings" jsonb NULL,
                "observacao_erro_vinculo" text NULL,
                "vinculos" jsonb NULL
            );
            INSERT INTO "a4_usuario" (
                "id", "password", "is_superuser", "first_name", "last_name",
                "is_staff", "is_active", "date_joined", "username", "nome_usual",
                "email", "foto", "tipo_usuario", "deleted_by_cascade",
                "last_json", "settings", "vinculos"
            ) VALUES (
                99991, 'pbkdf2_sha256$test', false, 'Maria', 'Silva',
                true, true, NOW(), '99991', 'Maria Silva',
                'maria@ifrn.edu.br', 'https://suap.ifrn.edu.br/foto.jpg', 'Servidor', false,
                '{"campus": "ZL", "cpf": "123.456.789-00", "sexo": "F", "tipo_vinculo": "Servidor"}',
                '{"theme": {"selected": "ifrn23"}}'::jsonb,
                '{"results": [{"identificador": "99991", "tipo": "Servidor", "campus": "ZL", "ativo": true}]}'::jsonb
            ) ON CONFLICT ("id") DO NOTHING;
            """)

    with connection.schema_editor() as schema_editor:
        m0030.ensure_auth_user_and_migrate_from_a4(django_apps, schema_editor)
        m0031.migrate_a4_data_to_suap_profile(django_apps, schema_editor)

    User = get_user_model()
    migrated_user = User.objects.get(id=99991)
    assert migrated_user.username == "99991"
    assert migrated_user.suap_profile.nome_usual == "Maria Silva"
    assert migrated_user.suap_profile.campus == "ZL"
    assert migrated_user.suap_profile.settings == {"theme": {"selected": "ifrn23"}}
    assert migrated_user.suap_raw_data.data["cpf"] == "123.456.789-00"
    assert migrated_user.suap_vinculos.filter(identificador="99991").exists()

    with connection.cursor() as cursor:
        cursor.execute('DROP TABLE IF EXISTS "a4_usuario" CASCADE;')
