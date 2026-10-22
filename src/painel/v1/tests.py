from unittest.mock import MagicMock, patch

import psycopg
import psycopg_pool
import pytest
import requests
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import DisallowedHost, SuspiciousOperation
from django.http import HttpResponse
from django.test import RequestFactory

from painel.middleware import ExceptionMiddleware
from painel.models import Ambiente, Curso


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


def _ambiente_teste():
    return Ambiente.objects.create(
        nome="Moodle de Teste", url="http://moodle-teste.ifrn.edu.br", token="token123", cor_mestra="#ffffff"
    )


def _resposta(status, corpo, reason="X"):
    resp = MagicMock()
    resp.ok = 200 <= status < 300
    resp.status_code = status
    resp.reason = reason
    resp.content = corpo.encode("utf-8")
    resp.headers = {}
    return resp


@pytest.mark.django_db
def test_get_json_api_404_usuario_nao_encontrado_nao_gera_evento():
    """#96: 404 'Usuário não encontrado.' do plugin é esperado: resultado vazio, sem erro nem evento Sentry."""
    from painel.v1.services import get_json_api

    corpo = '{"error": {"message": "Usuário não encontrado.", "code": 404}}'
    with (
        patch("painel.v1.services.requests.get", return_value=_resposta(404, corpo, "Not Found")),
        patch("painel.v1.services.sentry_sdk.capture_message") as capture,
        patch("painel.v1.services.logger") as log,
    ):
        assert get_json_api(_ambiente_teste(), "set_user_preference", username="x") is None

    capture.assert_not_called()
    log.error.assert_not_called()


@pytest.mark.django_db
def test_get_json_api_404_servico_inexistente_continua_sendo_falha():
    from painel.v1.services import MENSAGEM_FALHA_MOODLE, get_json_api

    corpo = '{"error": {"message": "Serviço não existe", "code": 404}}'
    with (
        patch("painel.v1.services.requests.get", return_value=_resposta(404, corpo, "Not Found")),
        patch("painel.v1.services.sentry_sdk.capture_message") as capture,
    ):
        assert get_json_api(_ambiente_teste(), "inexistente") is None

    capture.assert_called_once_with(MENSAGEM_FALHA_MOODLE, level="warning")


@pytest.mark.django_db
def test_get_json_api_resposta_nao_json_retorna_none():
    """#96: JSONDecodeError (ValueError) não pode virar 500."""
    from painel.v1.services import MENSAGEM_FALHA_MOODLE, get_json_api

    with (
        patch("painel.v1.services.requests.get", return_value=_resposta(200, "<html>erro</html>")),
        patch("painel.v1.services.sentry_sdk.capture_message") as capture,
    ):
        assert get_json_api(_ambiente_teste(), "enrol_course") is None

    capture.assert_called_once_with(MENSAGEM_FALHA_MOODLE, level="warning")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "erro",
    [
        requests.exceptions.ConnectTimeout("connect timeout"),
        requests.exceptions.SSLError("UNEXPECTED_EOF_WHILE_READING"),
        requests.exceptions.ConnectionError("Failed to resolve"),
    ],
)
def test_get_json_api_refaz_uma_vez_falha_de_conexao(erro):
    from painel.v1.services import get_json_api

    with (
        patch("painel.v1.services.time.sleep"),
        patch("painel.v1.services.requests.get", side_effect=[erro, _resposta(200, '{"ok": true}')]) as get,
    ):
        assert get_json_api(_ambiente_teste(), "get_diarios") == {"ok": True}

    assert get.call_count == 2


@pytest.mark.django_db
def test_get_json_api_falha_de_conexao_persistente_vai_para_uma_issue_unica_nivel_warning():
    from painel.v1.services import MENSAGEM_FALHA_MOODLE, get_json_api

    with (
        patch("painel.v1.services.time.sleep"),
        patch("painel.v1.services.requests.get", side_effect=requests.exceptions.ConnectTimeout("t")) as get,
        patch("painel.v1.services.sentry_sdk.capture_message") as capture,
        patch("painel.v1.services.logger") as log,
    ):
        assert get_json_api(_ambiente_teste(), "get_diarios") is None

    assert get.call_count == 2
    capture.assert_called_once_with(MENSAGEM_FALHA_MOODLE, level="warning")
    log.warning.assert_called_once()
    log.error.assert_not_called()


@pytest.mark.django_db
def test_filtrar_autoinscricoes_monta_contexto_uma_vez():
    """#96: evita N+1 em suap_vinculos (um get_user_context por curso)."""
    from painel.v1.services import _filtrar_autoinscricoes

    user = get_user_model().objects.create_user(username="123")
    cursos = [{"restricoes_de_autoinscricao": "true"} for _ in range(5)]

    with patch("painel.v1.services.get_user_context", return_value={}) as ctx:
        assert len(_filtrar_autoinscricoes(cursos, user)) == 5

    ctx.assert_called_once()


@pytest.fixture
def usuario_com_diarios(transactional_db, settings):
    from django_suap_auth.profile.models import DadosBrutos, Perfil, Vinculo

    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    cache.clear()
    Ambiente.objects.update(active=False)
    user = get_user_model().objects.create_user(username="aluno-diarios")
    Perfil.objects.create(user=user)
    DadosBrutos.objects.create(user=user, data={"tipo_usuario": "Aluno"})
    Vinculo.objects.create(user=user, identificador=user.username, campus="ZL", ativo=True)
    ambientes = [
        Ambiente.objects.create(
            nome=f"Moodle {number}",
            url=f"https://moodle-{number}.invalid",
            token="fixture",
            cor_mestra="#000000",
        )
        for number in range(3)
    ]
    cursos = {ava.pk: Curso.objects.create(codigo=f"curso-{ava.pk}", nome=f"Curso {ava.pk}") for ava in ambientes}
    yield user, ambientes, cursos
    cache.clear()


@pytest.mark.parametrize("curso_no_cache", [False, True])
def test_get_diarios_reune_cursos_e_filtra_autoinscricoes(usuario_com_diarios, curso_no_cache):
    from painel.v1.services import get_diarios

    user, ambientes, cursos = usuario_com_diarios
    if curso_no_cache:
        for curso in cursos.values():
            cache.set(f"curso:{curso.codigo}", curso)

    def resposta_moodle(ambiente, servico, **params):
        return {
            "diarios": [{"id": 1, "fullname": "Diário", "curso_codigo": cursos[ambiente.pk].codigo}],
            "autoinscricoes": [
                {
                    "id": 2,
                    "fullname": "Curso para alunos de ZL",
                    "restricoes_de_autoinscricao": "tipo_usuario == 'Aluno' and outras_matriculas[0]['campus'] == 'ZL'",
                },
                {
                    "id": 3,
                    "fullname": "Curso para servidores",
                    "restricoes_de_autoinscricao": "tipo_usuario == 'Servidor'",
                },
            ],
        }

    with patch("painel.v1.services.get_json_api", side_effect=resposta_moodle):
        for _ in range(3):
            result = get_diarios(user.username, q="")

            assert {(d["ambiente"]["id"], d["curso"]["codigo"], d["curso"]["nome"]) for d in result["diarios"]} == {
                (ava.pk, cursos[ava.pk].codigo, cursos[ava.pk].nome) for ava in ambientes
            }
            assert {(c["ambiente"]["id"], c["id"], c["fullname"]) for c in result["autoinscricoes"]} == {
                (ava.pk, 2, "Curso para alunos de ZL") for ava in ambientes
            }


def test_get_diarios_preserva_outros_ambientes_apos_resposta_invalida(usuario_com_diarios):
    from painel.v1.services import get_diarios

    user, ambientes, cursos = usuario_com_diarios
    ambiente_com_falha = ambientes[0]

    def resposta_moodle(ambiente, servico, **params):
        diarios = [{"id": 1, "fullname": "Diário", "curso_codigo": cursos[ambiente.pk].codigo}]
        if ambiente.pk == ambiente_com_falha.pk:
            diarios.append(None)
        return {"diarios": diarios}

    with (
        patch("painel.v1.services.get_json_api", side_effect=resposta_moodle),
        patch("painel.v1.services.sentry_sdk.capture_exception"),
    ):
        for _ in range(3):
            result = get_diarios(user.username, q="")

            assert {(d["ambiente"]["id"], d["curso"]["codigo"], d["curso"]["nome"]) for d in result["diarios"]} == {
                (ava.pk, cursos[ava.pk].codigo, cursos[ava.pk].nome) for ava in ambientes[1:]
            }


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


def test_services_nao_usa_setting_oauth_obsoleto(settings):
    """Regressão Sentry AVA-PAINEL-190: o setting OAUTH foi renomeado para SUAP_AUTH."""
    import inspect

    from painel.v1 import services

    assert "settings.OAUTH" not in inspect.getsource(services)
    assert settings.SUAP_AUTH["BASE_URL"]


@pytest.mark.django_db
def test_check_autoinscricao_usa_dados_brutos_e_vinculos_do_usuario():
    """Regressão #85: o contexto das regras vem de user.suap_raw_data e user.suap_vinculos."""
    from django_suap_auth.profile.models import DadosBrutos, Perfil, Vinculo

    from painel.v1.services import check_autoinscricao, get_user_context

    user = get_user_model().objects.create_user(username="20252154360129")
    Perfil.objects.create(user=user)
    DadosBrutos.objects.create(user=user, data={"tipo_usuario": "Aluno"})
    Vinculo.objects.create(
        user=user,
        identificador="20252154360129",
        tipo="aluno",
        ativo=True,
        modalidade="Técnico integrado ao ensino médio",
        detalhamento={"ativo": True, "modalidade": "Técnico integrado ao ensino médio"},
    )
    user = get_user_model().objects.get(pk=user.pk)

    contexto = get_user_context(user)
    assert contexto["tipo_usuario"] == "Aluno"
    assert len(contexto["outras_matriculas"]) == 1
    assert check_autoinscricao("tipo_usuario in ['Aluno']", user) is True
    assert check_autoinscricao("tipo_usuario in ['Servidor']", user) is False


@pytest.mark.django_db
def test_check_autoinscricao_erro_na_regra_vai_para_uma_issue_unica_nivel_info():
    """#86: falha ao avaliar a regra não é erro; agrupa num fingerprint fixo e loga em warning."""
    from painel.v1.services import MENSAGEM_REGRA_NAO_AVALIADA, check_autoinscricao

    user = get_user_model().objects.create_user(username="123")

    with patch("painel.v1.services.sentry_sdk.capture_message") as capture, patch("painel.v1.services.logger") as log:
        assert check_autoinscricao("chave_inexistente == 'x'", user) is False

    capture.assert_called_once_with(MENSAGEM_REGRA_NAO_AVALIADA, level="info")
    log.warning.assert_called_once()
    log.error.assert_not_called()


def test_wait_db_tenta_novamente_ate_o_banco_aceitar_conexoes():
    """#87: _wait_db aguarda o banco em vez de falhar na primeira tentativa."""
    import manage

    conexao = patch("manage.psycopg.connect").start()
    try:
        conexao.side_effect = [
            psycopg.OperationalError("refused"),
            psycopg.OperationalError("refused"),
            conexao.return_value,
        ]
        with patch("manage.time.sleep") as sleep:
            manage._wait_db(timeout=60, interval=0)
        assert conexao.call_count == 3
        assert sleep.call_count == 2
    finally:
        patch.stopall()


def test_wait_db_levanta_erro_claro_ao_esgotar_o_tempo():
    import manage

    with patch("manage.psycopg.connect", side_effect=psycopg.OperationalError("refused")), patch("manage.time.sleep"):
        with pytest.raises(RuntimeError, match="não respondeu"):
            manage._wait_db(timeout=0, interval=0)


@pytest.mark.django_db
def test_migration_0031_aceita_a4_usuario_sem_coluna_vinculos():
    """Regressão #88: dumps antigos de a4_usuario não têm a coluna vinculos."""
    import importlib

    from django.apps import apps as django_apps
    from django.db import connection

    if connection.vendor != "postgresql":
        pytest.skip("requer PostgreSQL")

    m0031 = importlib.import_module("painel.migrations.0031_migrate_a4_data_to_suap_profile")
    user = get_user_model().objects.create_user(username="99992", id=99992)

    with connection.cursor() as cursor:
        cursor.execute("""
            CREATE TABLE "a4_usuario" (
                "id" bigint NOT NULL PRIMARY KEY, "username" text, "nome_usual" text, "nome_social" text,
                "nome_registro" text, "nome" text, "email" text, "email_secundario" text,
                "email_google_classroom" text, "email_academico" text, "foto" text, "tipo_usuario" text,
                "settings" jsonb NULL, "first_login" timestamp with time zone NULL, "last_json" text NULL
            );
            INSERT INTO "a4_usuario" ("id", "username", "nome_usual", "last_json")
            VALUES (99992, '99992', 'Sem Vinculos', '{"campus": "ZL"}');
            """)

    with connection.schema_editor() as schema_editor:
        m0031.migrate_a4_data_to_suap_profile(django_apps, schema_editor)

    assert get_user_model().objects.get(pk=user.pk).suap_profile.nome_usual == "Sem Vinculos"
    with connection.cursor() as cursor:
        cursor.execute('DROP TABLE IF EXISTS "a4_usuario" CASCADE;')


@pytest.mark.django_db
def test_migration_0027_ensure_auth_user_e_idempotente():
    """Regressão #88: a 0027 garante auth_user antes de criar FKs; deve ser segura se já existir."""
    import importlib

    from django.apps import apps as django_apps
    from django.db import connection

    m0027 = importlib.import_module("painel.migrations.0027_configuracaoaba_historicalconfiguracaoaba")
    with connection.schema_editor() as schema_editor:
        m0027.ensure_auth_user(django_apps, schema_editor)


@pytest.mark.django_db
def test_usuario_info_usa_foto_75x100_quando_150x200_vazia():
    """Regressão #89: o login SUAP grava só url_foto_75x100."""
    from django_suap_auth.profile.models import DadosBrutos, Perfil

    from painel.v2.services import UsuarioService

    user = get_user_model().objects.create_user(username="2080882")
    Perfil.objects.create(user=user, nome_usual="Kelson Medeiros", url_foto_75x100="https://suap/foto/75x100/")
    DadosBrutos.objects.create(user=user, data={"foto": "https://suap/dados/foto/"})

    info = UsuarioService.info("2080882")

    assert info["nome_usual"] == "Kelson Medeiros"
    assert info["foto"] == info["url_foto_150x200"] == info["url_foto_75x100"] == "https://suap/foto/75x100/"


@pytest.mark.django_db
def test_usuario_info_foto_cai_para_dados_brutos():
    from django_suap_auth.profile.models import DadosBrutos, Perfil

    from painel.v2.services import UsuarioService

    user = get_user_model().objects.create_user(username="2080883")
    Perfil.objects.create(user=user)
    DadosBrutos.objects.create(user=user, data={"foto": "https://suap/dados/foto/"})

    assert UsuarioService.info("2080883")["foto"] == "https://suap/dados/foto/"


@pytest.mark.django_db
def test_sidebar_mostra_nome_usual_e_foto_do_suap_profile(client):
    """Regressão #90: show_name e foto_url ficam em user.suap_profile, não em auth.User."""
    from django_suap_auth.profile.models import Perfil

    user = get_user_model().objects.create_user(username="2080882")
    Perfil.objects.create(user=user, nome_usual="Kelson Medeiros", url_foto_75x100="https://suap/foto/75x100/")
    client.force_login(user)

    response = client.get("/")

    assert response.status_code == 200
    html = response.content.decode()
    assert "Kelson Medeiros" in html
    assert "https://suap/foto/75x100/" in html


@pytest.mark.django_db
def test_set_user_preference_grava_settings_no_perfil(client):
    """Regressão #94: settings fica em Perfil, não em auth.User."""
    from django_suap_auth.profile.models import Perfil

    user = get_user_model().objects.create_user(username="2080882")
    client.force_login(user)

    with patch("painel.v1.api.set_user_preference"):
        response = client.get(
            "/api/v1/set_user_preference/", {"category": "accessibility", "key": "dyslexia_friendly", "value": "true"}
        )

    assert response.status_code == 200
    assert Perfil.objects.get(user=user).settings == {"accessibility": {"dyslexia_friendly": True}}


@pytest.mark.django_db
def test_get_diarios_nao_usa_orm_nas_threads_do_pool():
    """Chamado #561508: ORM em thread do ThreadPoolExecutor abre uma conexão por thread que nunca é fechada."""
    import threading

    from painel.v1.services import get_diarios

    get_user_model().objects.create_user(username="123")
    principal = threading.get_ident()
    threads_orm = []
    threads_http = []

    def _get_json_api(*args, **kwargs):
        threads_http.append(threading.get_ident())
        return {
            "diarios": [
                {
                    "shortname": "x",
                    "curso_codigo": "123",
                    "diario_id": 1,
                    "viewurl": "http://moodle/course/view.php?id=1",
                }
            ],
            "autoinscricoes": [{"id": 1, "restricoes_de_autoinscricao": "true"}],
        }

    def _contexto(*args, **kwargs):
        threads_orm.append(threading.get_ident())
        return {}

    def _filter(*args, **kwargs):
        threads_orm.append(threading.get_ident())
        return MagicMock(first=MagicMock(return_value=None))

    cache = MagicMock()
    cache.get.return_value = None
    with (
        patch("painel.v1.services.Ambiente.cached", return_value=[_ambiente_teste()]),
        patch("painel.v1.services.Ambiente.as_dict", return_value=[]),
        patch("painel.v1.services.get_json_api", side_effect=_get_json_api),
        patch("painel.v1.services.get_user_context", side_effect=_contexto),
        patch("painel.v1.services.Curso.objects") as curso_objects,
        patch("painel.v1.services.cache", cache),
        patch("painel.v1.services.connections") as connections,
    ):
        curso_objects.filter.side_effect = _filter
        resultado = get_diarios("123")

    assert len(resultado["diarios"]) == 1
    assert len(resultado["autoinscricoes"]) == 1
    assert threads_http
    assert principal not in threads_http, "a consulta ao Moodle deve rodar em thread auxiliar"
    assert threads_orm and set(threads_orm) == {principal}, "ORM só pode rodar na thread da requisição"
    connections.close_all.assert_called()
