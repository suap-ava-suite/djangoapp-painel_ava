"""Preferências do usuário gravadas pelas views do painel (tema, posição do menu e tour)."""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from painel.models import Theme


@pytest.fixture
def cliente_com_perfil(db):
    from django_suap_auth.profile.models import Perfil

    user = get_user_model().objects.create_user(username="pref-aluno")
    perfil = Perfil.objects.create(user=user, settings=None)
    client = Client()
    client.force_login(user)
    return client, perfil


def test_change_theme_grava_o_tema_ativo(cliente_com_perfil):
    client, perfil = cliente_com_perfil
    Theme.objects.create(nome="ifrn23", apelido="Outono de 2023", active=True)

    resposta = client.get("/change_theme/ifrn23/")

    assert resposta.status_code == 302
    perfil.refresh_from_db()
    assert perfil.settings["theme"]["selected"] == "ifrn23"


def test_change_theme_ignora_tema_inexistente(cliente_com_perfil):
    client, perfil = cliente_com_perfil
    assert client.get("/change_theme/nao-existe/").status_code == 302
    perfil.refresh_from_db()
    assert not perfil.settings


@pytest.mark.parametrize("posicao", ["top", "bottom"])
def test_change_menu_position_grava_posicao_valida(cliente_com_perfil, posicao):
    client, perfil = cliente_com_perfil
    resposta = client.post("/settings/menu-position/", {"position": posicao})
    assert resposta.json() == {"status": "ok", "position": posicao}
    perfil.refresh_from_db()
    assert perfil.settings["menu_position"] == posicao


def test_change_menu_position_recusa_valor_invalido(cliente_com_perfil):
    client, _ = cliente_com_perfil
    assert client.post("/settings/menu-position/", {"position": "meio"}).status_code == 400


def test_tour_comeca_pendente_e_fica_concluido(cliente_com_perfil):
    client, perfil = cliente_com_perfil
    assert client.get("/get_tour_status/").json() == {"completed_tour": False}

    assert client.get("/set_tour_completed/").json() == {"status": "ok"}

    perfil.refresh_from_db()
    assert perfil.settings["tour"]["completed"] is True
    assert client.get("/get_tour_status/").json() == {"completed_tour": True}
