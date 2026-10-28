import re
from pathlib import Path
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from painel.models import Ambiente

CSS_POPUP = Path(__file__).parents[1] / "theme_ifrn25/static/theme/ifrn25/css/modals/popup-modal.css"


@pytest.fixture
def ambiente(db):
    return Ambiente.objects.create(
        nome="Moodle de Teste", url="http://moodle-teste.ifrn.edu.br", token="token123", cor_mestra="#ffffff"
    )


@pytest.fixture
def cliente_personificando(db):
    """Superusuário logado personificando o usuário "aluno" (sessão como em django_suap_auth.impersonation)."""
    User = get_user_model()
    admin = User.objects.create_superuser(username="admin", password="x", email="admin@exemplo.test")
    User.objects.create_user(
        username="aluno", password="x", first_name="Aluno", last_name="Teste", email="aluno@exemplo.test"
    )
    client = Client()
    client.force_login(admin)
    session = client.session
    session["impersonated_user"] = "aluno"
    session.save()
    return client


@patch("painel.views.get_json_api")
def test_inscricao_personificando_inscreve_o_usuario_personificado(mock_get_json_api, cliente_personificando, ambiente):
    mock_get_json_api.return_value = {"status": "enrolled"}

    response = cliente_personificando.post(f"/curso/{ambiente.id}/123/enrol/")

    assert response.status_code == 200
    kwargs = mock_get_json_api.call_args.kwargs
    assert kwargs["username"] == "aluno"
    assert (kwargs["firstname"], kwargs["lastname"], kwargs["email"]) == ("Aluno", "Teste", "aluno@exemplo.test")


@patch("painel.views.get_json_api")
def test_cancelamento_personificando_suspende_o_usuario_personificado(
    mock_get_json_api, cliente_personificando, ambiente
):
    mock_get_json_api.return_value = {"status": "unenrolled"}

    cliente_personificando.post(f"/curso/{ambiente.id}/123/unenrol/")

    assert mock_get_json_api.call_args.kwargs["username"] == "aluno"


@patch("painel.views.get_json_api")
def test_detalhes_personificando_consulta_o_usuario_personificado(mock_get_json_api, cliente_personificando, ambiente):
    mock_get_json_api.return_value = {"fullname": "Curso", "is_enrolled": False}

    response = cliente_personificando.get(f"/curso/{ambiente.id}/123/")

    assert response.status_code == 200
    assert mock_get_json_api.call_args.kwargs["username"] == "aluno"


@patch("painel.v1.services.get_json")
def test_get_json_api_codifica_os_valores_da_querystring(mock_get_json, ambiente):
    from painel.v1.services import get_json_api

    mock_get_json.return_value = {}
    get_json_api(ambiente, "enrol_course", courseid=1, lastname="da Silva & Souza", q="#2098", campus=None)

    url = mock_get_json.call_args.args[0]
    assert url.endswith("/?enrol_course&courseid=1&lastname=da+Silva+%26+Souza&q=%232098")


def test_bloco_do_codigo_do_erro_fica_oculto_com_a_classe_hidden():
    css = CSS_POPUP.read_text(encoding="utf-8")
    bloco = re.search(r"#aviso-modal-codigo\s*\{(?P<corpo>.*?)\n    \}", css, re.S)

    assert bloco, "regra #aviso-modal-codigo não encontrada"
    assert re.search(r"&\.hidden\s*\{\s*display:\s*none;", bloco["corpo"])
