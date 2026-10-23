import importlib

import pytest

import settings.securities as securities


@pytest.fixture
def recarregar_securities(monkeypatch):
    def _recarregar(**env):
        for chave in ("DJANGO_CSRF_TRUSTED_ORIGINS", "DJANGO_CSRF_COOKIE_DOMAIN", "DJANGO_CSRF_COOKIE_SECURE"):
            monkeypatch.delenv(chave, raising=False)
        for chave, valor in env.items():
            monkeypatch.setenv(chave, valor)
        return importlib.reload(securities)

    yield _recarregar
    monkeypatch.undo()
    importlib.reload(securities)


def test_csrf_usa_padroes_seguros_sem_variaveis(recarregar_securities):
    mod = recarregar_securities()
    assert mod.CSRF_TRUSTED_ORIGINS == []
    assert mod.CSRF_COOKIE_DOMAIN is None
    assert mod.CSRF_COOKIE_SECURE is False


def test_csrf_trusted_origins_vem_do_ambiente(recarregar_securities):
    mod = recarregar_securities(DJANGO_CSRF_TRUSTED_ORIGINS="https://ava.ifrn.edu.br")
    assert mod.CSRF_TRUSTED_ORIGINS == ["https://ava.ifrn.edu.br"]


def test_csrf_trusted_origins_aceita_varios_valores(recarregar_securities):
    mod = recarregar_securities(DJANGO_CSRF_TRUSTED_ORIGINS="https://ava.ifrn.edu.br,https://painel.ava.ifrn.edu.br")
    assert mod.CSRF_TRUSTED_ORIGINS == ["https://ava.ifrn.edu.br", "https://painel.ava.ifrn.edu.br"]


def test_csrf_cookie_domain_e_secure_vem_do_ambiente(recarregar_securities):
    mod = recarregar_securities(DJANGO_CSRF_COOKIE_DOMAIN="ava.ifrn.edu.br", DJANGO_CSRF_COOKIE_SECURE="True")
    assert mod.CSRF_COOKIE_DOMAIN == "ava.ifrn.edu.br"
    assert mod.CSRF_COOKIE_SECURE is True


def test_post_com_origin_confiavel_passa_na_verificacao_csrf(settings):
    from django.test import Client

    settings.CSRF_TRUSTED_ORIGINS = ["https://ava.ifrn.edu.br"]
    settings.ALLOWED_HOSTS = ["*"]
    c = Client(enforce_csrf_checks=True)
    c.cookies["csrftoken"] = "a" * 32
    resposta = c.post(
        "/curso/1/1/enrol/",
        HTTP_ORIGIN="https://ava.ifrn.edu.br",
        HTTP_X_CSRFTOKEN="a" * 32,
        HTTP_HOST="ava.ifrn.edu.br",
    )
    # Passou do CSRF; sem login, o decorator redireciona (302) em vez de 403.
    assert resposta.status_code == 302


def test_post_com_origin_nao_confiavel_e_barrado_pelo_csrf(settings):
    from django.test import Client

    settings.CSRF_TRUSTED_ORIGINS = []
    settings.ALLOWED_HOSTS = ["*"]
    c = Client(enforce_csrf_checks=True)
    c.cookies["csrftoken"] = "a" * 32
    resposta = c.post(
        "/curso/1/1/enrol/",
        HTTP_ORIGIN="https://ava.ifrn.edu.br",
        HTTP_X_CSRFTOKEN="a" * 32,
        HTTP_HOST="ava.ifrn.edu.br",
        secure=False,
    )
    assert resposta.status_code == 403
