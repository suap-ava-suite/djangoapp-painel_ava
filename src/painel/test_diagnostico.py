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


@pytest.mark.parametrize("rota", ["usuario", "autoinscricao", "exportar"])
def test_anonimo_e_usuario_comum_recebem_403(usuarios, rota):
    _, _, aluno = usuarios
    assert Client().get(f"/diagnostico/x/{rota}/").status_code == 403
    assert _cliente(aluno).get(f"/diagnostico/x/{rota}/").status_code == 403


@pytest.mark.parametrize("rota", ["usuario", "autoinscricao", "exportar"])
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
    assert por_ambiente[a0.id]["conta"]["url"] == "https://moodle-0.invalid/user/profile.php?id=7"
    assert por_ambiente[a1.id]["status"] == "endpoint_indisponivel"
    assert por_ambiente[a1.id]["conta"] is None


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
    falha = next(a for a in dados["ambientes"] if a["ambiente"]["id"] == a1.id)
    assert falha["mensagem"] == "O Moodle não respondeu a tempo."
    assert falha["detalhe"] == "ConnectTimeout"  # sem o texto da exceção


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
    assert por_ambiente[a0.id]["mensagem"] == "O Moodle respondeu com erro HTTP 401."
    assert por_ambiente[a0.id]["detalhe"] == "HTTP 401"
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


def test_usuario_traz_link_de_edicao_no_admin(usuarios, ambientes):
    admin, _, aluno = usuarios
    Ambiente.objects.update(active=False)
    cache.clear()
    dados = _cliente(admin).get("/diagnostico/20261234/usuario/").json()
    assert (
        dados["usuario"]["url_editar"] == f"/admin/{aluno._meta.app_label}/{aluno._meta.model_name}/{aluno.pk}/change/"
    )


def test_exportar_baixa_o_mesmo_json_do_admin(usuarios):
    admin, _, _ = usuarios
    resposta = _cliente(admin).get("/diagnostico/20261234/exportar/")
    assert resposta.status_code == 200
    assert resposta["Content-Type"].startswith("application/json")
    assert resposta["Content-Disposition"].startswith('attachment; filename="usuarios-suap-20261234-')
    payload = json.loads(resposta.content)
    assert payload["formato"]
    assert [u["user"]["username"] for u in payload["usuarios"]] == ["20261234"]


def test_exportar_usuario_inexistente(usuarios):
    admin, _, _ = usuarios
    resposta = _cliente(admin).get("/diagnostico/inexistente/exportar/")
    assert resposta.status_code == 404
    assert resposta.json() == {"error": "O usuário não existe no Painel."}


def test_exportar_nao_aceita_post(usuarios):
    admin, _, _ = usuarios
    assert _cliente(admin).post("/diagnostico/20261234/exportar/").status_code == 405


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
    assert c[1]["url"] == "https://moodle-0.invalid/course/view.php?id=1"

    assert c[2]["atende"] is False and c[2]["motivo"] == MOTIVO_REGRA_FALSA
    assert [x["atendido"] for x in c[2]["arvore"]["raiz"]["filhos"]] == [True, False]
    assert c[2]["indices_que_atenderiam"] == [1]
    assert c[2]["campos_da_regra"] == {"tipo_usuario": "Aluno"}
    assert c[2]["inscricao"] == "nenhuma"

    assert c[3]["atende"] is True and c[3]["aparece_no_painel"] is False and c[3]["inscricao"] == "expirada"
    assert c[4]["motivo"] == MOTIVO_REGRA_INVALIDA and c[4]["detalhe"] and c[4]["inscricao"] == "suspensa"

    assert por_ambiente[a1.id]["fonte"] == "get_diarios"
    assert por_ambiente[a1.id]["cursos"][0]["courseid"] == 9
    assert por_ambiente[a1.id]["cursos"][0]["url"] == "https://moodle-1.invalid/course/view.php?id=9"
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
    assert "/diagnostico/__username__/exportar/" in html_admin
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


def _http_sem_json(status):
    exc = HTTPException(f"{status}")
    exc.status = status
    exc.body = "<html>erro</html>"
    return exc


@pytest.mark.parametrize(
    "falha,mensagem,detalhe",
    [
        (_http_sem_json(502), "O Moodle respondeu com erro HTTP 502.", "HTTP 502"),
        (requests.exceptions.ConnectionError("recusada"), "Não foi possível conectar ao Moodle.", "ConnectionError"),
        (requests.exceptions.ReadTimeout("lento"), "O Moodle não respondeu a tempo.", "ReadTimeout"),
        (requests.exceptions.TooManyRedirects("loop"), "Resposta inválida do Moodle.", "TooManyRedirects"),
        (ValueError("json"), "Resposta inválida do Moodle.", "ValueError"),
    ],
)
def test_chamar_moodle_classifica_falhas(ambientes, falha, mensagem, detalhe):
    with patch("painel.diagnostico.get_json", side_effect=falha):
        with pytest.raises(diagnostico.MoodleIndisponivel) as erro:
            diagnostico._chamar_moodle(ambientes[0], "get_diagnostico_usuario", username="x")
    assert erro.value.status == "erro"
    assert erro.value.mensagem == mensagem
    assert detalhe in erro.value.detalhe


@pytest.mark.parametrize(
    "id_moodle,esperado",
    [(5, "https://m.test/x.php?id=5"), ("5", "https://m.test/x.php?id=5"), (None, None), ("1&a=b", None)],
)
def test_url_moodle_so_aceita_id_inteiro(id_moodle, esperado):
    assert diagnostico._url_moodle("https://m.test", "x.php", id_moodle) == esperado


@pytest.mark.parametrize("email,esperado", [("", ""), (None, ""), ("sem-arroba", ""), ("ab@x.test", "ab***@x.test")])
def test_mascarar_email(email, esperado):
    assert diagnostico._mascarar_email(email) == esperado


REGRA_EJA = (
    "tipo_usuario in ['Aluno'] and $any([m['tipo'] == 'aluno' and m['detalhamento']['ativo'] == true "
    "and m['detalhamento']['modalidade'] in ['Técnico integrado ao ensino médio EJA', 'Técnico subsequente'] "
    "for m in outras_matriculas])"
)
CONTEXTO_EJA = {
    "tipo_usuario": "Aluno",
    "cpf": "000",
    "outras_matriculas": [
        {"tipo": "aluno", "detalhamento": {"ativo": True, "modalidade": "Técnico Integrado"}},
        {"tipo": "Aluno", "detalhamento": {"ativo": False, "modalidade": "Técnico subsequente"}},
    ],
}


def _curso(regra):
    return {"courseid": 1, "fullname": "X", "visible": True, "restricoes_de_autoinscricao": regra}


def test_avaliar_curso_usa_explain_tree_da_django_rule_engine(usuarios):
    _, _, aluno = usuarios
    curso = diagnostico._avaliar_curso(_curso(REGRA_EJA), aluno, CONTEXTO_EJA, "https://moodle.invalid")

    arvore = curso["arvore"]
    assert arvore["atendido"] is False
    contem, funcao = arvore["raiz"]["filhos"]
    assert contem["tipo"] == "contem" and contem["atendido"] is True
    assert contem["esquerda"]["rotulo"] == "tipo_usuario" and contem["esquerda"]["valor"] == "Aluno"

    comp = funcao["argumentos"][0]
    assert funcao["nome"] == "$any" and comp["tipo"] == "compreensao" and comp["total"] == 2
    primeiro, segundo = comp["itens"]
    assert [f["atendido"] for f in primeiro["expressao"]["filhos"]] == [True, True, False]
    assert [f["atendido"] for f in segundo["expressao"]["filhos"]] == [False, False, True]
    modalidade = primeiro["expressao"]["filhos"][2]
    assert modalidade["esquerda"]["rotulo"] == "m.detalhamento.modalidade"
    assert modalidade["esquerda"]["valor"] == "Técnico Integrado"
    assert curso["atende"] is False and curso["motivo"] == MOTIVO_REGRA_FALSA


def test_rotulo_dos_vinculos_usa_campus_e_curso_sem_identificador(usuarios):
    _, _, aluno = usuarios
    contexto = {
        "tipo_usuario": "Aluno",
        "outras_matriculas": [
            {"identificador": "20250000000001", "campus": "ZN", "curso": "Eletrônica", "tipo": "aluno"},
            {"identificador": "20250000000002", "tipo": "aluno", "detalhamento": {"curso": "FIC"}},
        ],
    }
    curso = diagnostico._avaliar_curso(
        _curso("$any([m['tipo'] == 'x' for m in outras_matriculas])"), aluno, contexto, "https://moodle.invalid"
    )
    itens = curso["arvore"]["raiz"]["argumentos"][0]["itens"]
    assert [i["rotulo"] for i in itens] == ["ZN · Eletrônica", "FIC"]
    assert diagnostico._rotulo_matricula("x") == ""


def test_avaliar_curso_oculta_campos_sensiveis_do_painel(usuarios):
    _, _, aluno = usuarios
    curso = diagnostico._avaliar_curso(_curso("cpf == '123'"), aluno, CONTEXTO_EJA, "https://moodle.invalid")
    lado = curso["arvore"]["raiz"]["esquerda"]
    assert lado["sensivel"] is True and lado["valor"] is None
    assert curso["arvore"]["raiz"]["atendido"] is False


def test_avaliar_curso_que_atende_nao_detalha(usuarios):
    _, _, aluno = usuarios
    curso = diagnostico._avaliar_curso(_curso("tipo_usuario == 'Aluno'"), aluno, CONTEXTO_EJA, "https://moodle.invalid")
    assert curso["atende"] is True and curso["arvore"] is None
