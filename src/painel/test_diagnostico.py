import json
import shutil
import subprocess  # noqa: S404
from http.client import HTTPException
from pathlib import Path
from unittest.mock import patch

import pytest
import requests
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.template.loader import render_to_string
from django.test import Client

from painel import diagnostico
from painel.models import Ambiente
from painel.v1.services import (
    MOTIVO_ERRO_AVALIACAO,
    MOTIVO_OK,
    MOTIVO_REGRA_FALSA,
    MOTIVO_REGRA_INVALIDA,
    MOTIVO_REGRA_VAZIA,
    MOTIVO_USUARIO_INEXISTENTE,
    avaliar_autoinscricao,
)

TESTES_JS = Path(__file__).parent / "tests_js"
REGRA_ZN = "tipo_usuario == 'Aluno' and outras_matriculas[0]['campus'] == 'ZN'"


@pytest.fixture
def ambientes(db, settings):
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    cache.clear()
    Ambiente.objects.update(active=False)
    criados = [
        Ambiente.objects.create(nome=f"Moodle {n}", url=f"https://moodle-{n}.invalid", token="t", cor_mestra="#000")
        for n in range(2)
    ]
    yield criados
    cache.clear()


@pytest.fixture
def usuarios(db):
    from django_suap_auth.profile.models import DadosBrutos, Perfil, Vinculo

    User = get_user_model()
    admin = User.objects.create_superuser(username="admin", password="x", email="admin@exemplo.test")
    outro_admin = User.objects.create_superuser(username="admin2", password="x", email="a2@exemplo.test")
    aluno = User.objects.create_user(
        username="20261234", first_name="Ester", last_name="Teste", email="ester@exemplo.test"
    )
    Perfil.objects.create(user=aluno, tipo_usuario="Aluno", campus="ZN", curso="Informática", cpf="000.000.000-00")
    DadosBrutos.objects.create(
        user=aluno, data={"tipo_usuario": "Aluno", "campus": "ZN", "cpf": "000.000.000-00", "email": "e@x.test"}
    )
    # O vínculo certo (ZN) está no índice 1: regras com outras_matriculas[0] falham
    Vinculo.objects.create(user=aluno, identificador="2025A", tipo="Aluno", campus="CNAT", ativo=False)
    Vinculo.objects.create(user=aluno, identificador="2026B", tipo="Aluno", campus="ZN", ativo=True)
    return admin, outro_admin, aluno


def _cliente(user):
    client = Client()
    client.force_login(user)
    return client


def _erro_http(status, mensagem):
    exc = HTTPException(f"{status}")
    exc.status = status
    exc.body = json.dumps({"error": {"message": mensagem, "code": status}})
    return exc


def _moodle(respostas):
    """Simula get_json: respostas[(ambiente_url, servico)] = dict ou exceção."""

    def fake(url, headers=None, **kwargs):
        for (base, servico), resposta in respostas.items():
            if url.startswith(f"{base}/admin/tool/painelava/api/?{servico}&"):
                if isinstance(resposta, Exception):
                    raise resposta
                return resposta
        raise AssertionError(f"URL inesperada: {url}")

    return patch("painel.diagnostico.get_json", side_effect=fake)


def _diag(exists=True, autoinscricoes=None):
    dados = {"exists": exists, "autoinscricoes": autoinscricoes or []}
    if exists:
        dados["user"] = {"id": 7, "username": "20261234", "suspended": False, "lastaccess": 1790000000}
        dados["enrolments"] = {"active": 3, "suspended": 1, "total": 4}
    return dados


# --- Acesso -----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("rota", ["usuario", "autoinscricao"])
def test_anonimo_e_usuario_comum_recebem_403(usuarios, rota):
    _, _, aluno = usuarios
    assert Client().get(f"/diagnostico/x/{rota}/").status_code == 403
    assert _cliente(aluno).get(f"/diagnostico/x/{rota}/").status_code == 403


@pytest.mark.parametrize("rota", ["usuario", "autoinscricao"])
def test_recusa_durante_personificacao(usuarios, rota):
    admin, _, _ = usuarios
    client = _cliente(admin)
    session = client.session
    session["impersonated_user"] = "20261234"
    session.save()
    resposta = client.get(f"/diagnostico/20261234/{rota}/")
    assert resposta.status_code == 409


def test_post_nao_permitido(usuarios):
    admin, _, _ = usuarios
    assert _cliente(admin).post("/diagnostico/20261234/usuario/").status_code == 405


# --- Aba Personificar -------------------------------------------------------------------------------------------


def test_usuario_com_status_por_ambiente(usuarios, ambientes):
    admin, _, _ = usuarios
    a0, a1 = ambientes
    with _moodle(
        {
            (a0.url, "get_diagnostico_usuario"): _diag(),
            (a1.url, "get_diagnostico_usuario"): _erro_http(404, "Serviço não existe"),
        }
    ):
        dados = _cliente(admin).get("/diagnostico/20261234/usuario/").json()

    assert dados["existe_no_painel"] is True
    assert dados["pode_personificar"] is True
    usuario = dados["usuario"]
    assert usuario["nome"] == "Ester Teste"
    assert usuario["email"] == "es***@exemplo.test"
    assert usuario["perfil"]["campus"] == "ZN"
    assert [m["campus"] for m in usuario["matriculas"]] == ["CNAT", "ZN"]
    assert "000.000.000-00" not in json.dumps(dados)

    por_ambiente = {a["ambiente"]["id"]: a for a in dados["ambientes"]}
    assert por_ambiente[a0.id]["status"] == "ok"
    assert por_ambiente[a0.id]["inscricoes"] == {"active": 3, "suspended": 1, "total": 4}
    assert por_ambiente[a1.id]["status"] == "endpoint_indisponivel"


def test_usuario_sem_conta_e_erro_de_rede(usuarios, ambientes):
    admin, _, _ = usuarios
    a0, a1 = ambientes
    with _moodle(
        {
            (a0.url, "get_diagnostico_usuario"): _diag(exists=False),
            (a1.url, "get_diagnostico_usuario"): requests.exceptions.ConnectTimeout("lento"),
        }
    ):
        dados = _cliente(admin).get("/diagnostico/20261234/usuario/").json()
    status = {a["ambiente"]["id"]: a["status"] for a in dados["ambientes"]}
    assert status == {a0.id: "sem_conta", a1.id: "erro"}


def test_erro_http_generico_do_moodle(usuarios, ambientes):
    admin, _, _ = usuarios
    a0, a1 = ambientes
    with _moodle(
        {
            (a0.url, "get_diagnostico_usuario"): _erro_http(401, "Unauthorized"),
            (a1.url, "get_diagnostico_usuario"): ["inesperado"],
        }
    ):
        dados = _cliente(admin).get("/diagnostico/20261234/usuario/").json()
    por_ambiente = {a["ambiente"]["id"]: a for a in dados["ambientes"]}
    assert por_ambiente[a0.id]["status"] == "erro"
    assert "Unauthorized" in por_ambiente[a0.id]["mensagem"]
    assert por_ambiente[a1.id]["status"] == "erro"


@pytest.mark.parametrize(
    "alvo,motivo",
    [("admin2", "alvo_superuser"), ("admin", "proprio_usuario"), ("inexistente", "inexistente")],
)
def test_personificacao_bloqueada(usuarios, ambientes, alvo, motivo):
    admin, _, _ = usuarios
    Ambiente.objects.update(active=False)
    cache.clear()
    dados = _cliente(admin).get(f"/diagnostico/{alvo}/usuario/").json()
    assert dados["pode_personificar"] is False
    assert dados["motivo_bloqueio"] == motivo


def test_personificacao_bloqueada_para_inativo(usuarios, ambientes):
    admin, _, aluno = usuarios
    aluno.is_active = False
    aluno.save()
    Ambiente.objects.update(active=False)
    cache.clear()
    dados = _cliente(admin).get("/diagnostico/20261234/usuario/").json()
    assert dados["motivo_bloqueio"] == "inativo"


# --- Aba Auto inscrição -----------------------------------------------------------------------------------------


def test_autoinscricao_explica_por_que_nao_atende(usuarios, ambientes):
    admin, _, _ = usuarios
    a0, a1 = ambientes
    cursos = [
        {
            "courseid": 1,
            "fullname": "Extensão",
            "visible": True,
            "restricoes_de_autoinscricao": "tipo_usuario == 'Aluno'",
            "enrolment": {"status": "active"},
        },
        {
            "courseid": 2,
            "fullname": "Pesquisa",
            "visible": True,
            "restricoes_de_autoinscricao": REGRA_ZN,
            "enrolment": None,
        },
        {
            "courseid": 3,
            "fullname": "Oculto",
            "visible": False,
            "restricoes_de_autoinscricao": "tipo_usuario == 'Aluno'",
            "enrolment": {"status": "suspended", "expired": True},
        },
        {
            "courseid": 4,
            "fullname": "Quebrado",
            "visible": True,
            "restricoes_de_autoinscricao": "tipo_usuario ==",
            "enrolment": {"status": "suspended", "expired": False},
        },
    ]
    vitrine = [{"id": 9, "fullname": "Vitrine", "restricoes_de_autoinscricao": "campus == 'ZN'", "is_enrolled": True}]
    with _moodle(
        {
            (a0.url, "get_diagnostico_usuario"): _diag(autoinscricoes=cursos),
            (a1.url, "get_diagnostico_usuario"): _erro_http(404, "Serviço não existe"),
            (a1.url, "get_diarios"): {"autoinscricoes": vitrine},
        }
    ):
        dados = _cliente(admin).get("/diagnostico/20261234/autoinscricao/").json()

    assert "000.000.000-00" not in json.dumps(dados)
    assert "e@x.test" not in json.dumps(dados)
    por_ambiente = {a["ambiente"]["id"]: a for a in dados["ambientes"]}
    c = {x["courseid"]: x for x in por_ambiente[a0.id]["cursos"]}

    assert c[1]["atende"] is True and c[1]["motivo"] == MOTIVO_OK and c[1]["inscricao"] == "ativa"
    assert c[1]["aparece_no_painel"] is True

    assert c[2]["atende"] is False and c[2]["motivo"] == MOTIVO_REGRA_FALSA
    assert [x["resultado"] for x in c[2]["condicoes"]] == [True, False]
    assert c[2]["indices_que_atenderiam"] == [1]
    assert c[2]["campos_da_regra"] == {"tipo_usuario": "Aluno"}
    assert c[2]["inscricao"] == "nenhuma"

    assert c[3]["atende"] is True and c[3]["aparece_no_painel"] is False and c[3]["inscricao"] == "expirada"
    assert c[4]["motivo"] == MOTIVO_REGRA_INVALIDA and c[4]["detalhe"] and c[4]["inscricao"] == "suspensa"

    assert por_ambiente[a1.id]["fonte"] == "get_diarios"
    assert por_ambiente[a1.id]["cursos"][0]["courseid"] == 9
    assert por_ambiente[a1.id]["cursos"][0]["inscricao"] == "ativa"
    assert [m["campus"] for m in dados["contexto"]["matriculas"]] == ["CNAT", "ZN"]


def test_autoinscricao_usuario_inexistente_no_painel(usuarios, ambientes):
    admin, _, _ = usuarios
    a0, a1 = ambientes
    curso = {"courseid": 1, "fullname": "X", "visible": True, "restricoes_de_autoinscricao": "tipo_usuario == 'Aluno'"}
    with _moodle(
        {
            (a0.url, "get_diagnostico_usuario"): _diag(exists=False, autoinscricoes=[curso]),
            (a1.url, "get_diagnostico_usuario"): _erro_http(500, "boom"),
        }
    ):
        dados = _cliente(admin).get("/diagnostico/ninguem/autoinscricao/").json()
    por_ambiente = {a["ambiente"]["id"]: a for a in dados["ambientes"]}
    assert dados["existe_no_painel"] is False
    assert por_ambiente[a0.id]["cursos"][0]["motivo"] == MOTIVO_USUARIO_INEXISTENTE
    assert por_ambiente[a1.id]["fonte"] is None and por_ambiente[a1.id]["status"] == "erro"


def test_autoinscricao_fallback_tambem_falha(usuarios, ambientes):
    admin, _, _ = usuarios
    a0, a1 = ambientes
    with _moodle(
        {
            (a0.url, "get_diagnostico_usuario"): _erro_http(404, "Serviço não existe"),
            (a0.url, "get_diarios"): requests.exceptions.ConnectionError("x"),
            (a1.url, "get_diagnostico_usuario"): _diag(),
        }
    ):
        dados = _cliente(admin).get("/diagnostico/20261234/autoinscricao/").json()
    por_ambiente = {a["ambiente"]["id"]: a for a in dados["ambientes"]}
    assert por_ambiente[a0.id]["fonte"] is None and por_ambiente[a0.id]["status"] == "erro"
    assert por_ambiente[a1.id]["cursos"] == []


# --- Funções de apoio -------------------------------------------------------------------------------------------


def test_avaliar_autoinscricao_cobre_todos_os_motivos(usuarios):
    _, _, aluno = usuarios
    assert avaliar_autoinscricao("", aluno)[1] == MOTIVO_REGRA_VAZIA
    assert avaliar_autoinscricao("x == 1", None)[1] == MOTIVO_USUARIO_INEXISTENTE
    assert avaliar_autoinscricao("tipo_usuario ==", aluno)[1] == MOTIVO_REGRA_INVALIDA
    assert avaliar_autoinscricao("chave_inexistente == 'x'", aluno)[1] == MOTIVO_ERRO_AVALIACAO
    assert avaliar_autoinscricao("tipo_usuario == 'Servidor'", aluno)[:2] == (False, MOTIVO_REGRA_FALSA)
    assert avaliar_autoinscricao("tipo_usuario == 'Aluno'", aluno)[:2] == (True, MOTIVO_OK)


@pytest.mark.parametrize(
    "regra,partes",
    [
        ("a == 1 and b == 2", ["a == 1", "b == 2"]),
        ("(a == 1 or b == 'x and y')", ["a == 1", "b == 'x and y'"]),
        ("a == 1 and (b == 2 or c == 3)", ["a == 1", "(b == 2 or c == 3)"]),
        ("a == 1 and b == 2 or c == 3", []),
        ("a == 1", []),
        ("(a == 1) and (b == 2)", ["(a == 1)", "(b == 2)"]),
        ("brand == 1 and android == 2", ["brand == 1", "android == 2"]),
        ("a == 'it\\'s' and b", ["a == 'it\\'s'", "b"]),
    ],
)
def test_dividir_condicoes(regra, partes):
    assert diagnostico._dividir_condicoes(regra) == partes


def test_indices_que_atenderiam_ignora_erros():
    contexto = {"outras_matriculas": [{"campus": "ZN"}, {}]}
    regra = "outras_matriculas[0]['campus'] == 'ZN'"
    assert diagnostico._indices_que_atenderiam(regra, contexto) == [0]
    assert diagnostico._indices_que_atenderiam("x == 1", contexto) == []


# --- Templates e JS ---------------------------------------------------------------------------------------------


def test_menu_e_modal_so_para_superusuario(usuarios):
    admin, _, aluno = usuarios
    admins = [{"pk": 1, "nome": "Moodle", "url": "https://moodle.invalid/admin/"}]
    ctx = {"admins": admins, "ambientes": [], "personificando": False, "last_startup": "x"}
    perfil = "theme/ifrn25/frontpage/partials/modals/profile.html"
    foot = "theme/ifrn25/frontpage/partials/foot.html"

    assert "data-diagnostico-abrir" in render_to_string(perfil, {**ctx, "user": admin, "logged_user": admin})
    assert 'data-track-destino="diagnosticar"' in render_to_string(perfil, {**ctx, "user": admin, "logged_user": admin})
    assert "data-diagnostico-abrir" not in render_to_string(perfil, {**ctx, "user": aluno, "logged_user": aluno})

    html_admin = render_to_string(foot, {**ctx, "user": admin})
    assert 'id="diagnostico-modal"' in html_admin and "js/diagnostico.js" in html_admin
    assert "/diagnostico/__username__/usuario/" in html_admin
    html_aluno = render_to_string(foot, {**ctx, "user": aluno})
    assert "diagnostico-modal" not in html_aluno and "diagnostico.js" not in html_aluno
    html_personificando = render_to_string(foot, {**ctx, "user": admin, "personificando": True})
    assert "diagnostico-modal" not in html_personificando


def test_js_nao_usa_innerhtml():
    js = (Path(__file__).parents[1] / "theme_ifrn25/static/theme/ifrn25/js/diagnostico.js").read_text(encoding="utf-8")
    assert "innerHTML" not in js.replace("nunca innerHTML", "")


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js não instalado")
def test_suite_node_do_diagnostico_passa():
    resultado = subprocess.run(  # noqa: S603
        [shutil.which("node"), "--test", str(TESTES_JS / "diagnostico.test.js")],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
