import importlib
import tomllib

import pytest
from django.conf import settings
from django.template.loader import render_to_string

import settings.project as project


def test_versao_vem_do_pyproject():
    if not project.PYPROJECT.exists():
        pytest.skip("pyproject.toml fora do container: reconstrua a imagem ou monte o arquivo em /app")
    with project.PYPROJECT.open("rb") as arquivo:
        esperado = tomllib.load(arquivo)["project"]["version"]
    assert settings.APP_VERSION == esperado


@pytest.mark.parametrize(
    "conteudo",
    [None, "isto não é toml = = ", '[tool.x]\nversion = "1"\n'],
    ids=["sem_arquivo", "toml_invalido", "sem_project"],
)
def test_ler_versao_sem_pyproject_valido(tmp_path, conteudo):
    caminho = tmp_path / "pyproject.toml"
    if conteudo is not None:
        caminho.write_text(conteudo, encoding="utf-8")
    assert project.ler_versao(caminho) == project.VERSAO_DESCONHECIDA


def test_ler_versao(tmp_path):
    caminho = tmp_path / "pyproject.toml"
    caminho.write_text('[project]\nversion = "9.8.7"\n', encoding="utf-8")
    assert project.ler_versao(caminho) == "9.8.7"


@pytest.mark.parametrize(
    "ambiente,release",
    [("production", "1.2.3"), ("test", "1.2.3-test"), ("local", "1.2.3-local")],
)
def test_release_segue_o_nome_da_tag(ambiente, release):
    assert project.nome_da_release("1.2.3", ambiente) == release


@pytest.mark.parametrize(
    "valor,esperado", [(None, "local"), ("", "local"), (" test ", "test"), ("production", "production")]
)
def test_ambiente_vem_da_variavel_com_padrao_local(monkeypatch, valor, esperado):
    if valor is None:
        monkeypatch.delenv("APP_ENVIRONMENT", raising=False)
    else:
        monkeypatch.setenv("APP_ENVIRONMENT", valor)
    try:
        recarregado = importlib.reload(project)
        assert recarregado.APP_ENVIRONMENT == esperado
        assert recarregado.APP_RELEASE == project.nome_da_release(recarregado.APP_VERSION, esperado)
    finally:
        monkeypatch.undo()
        importlib.reload(project)


def test_modal_de_perfil_mostra_versao_e_ambiente(rf):
    html = render_to_string(
        "theme/ifrn25/frontpage/partials/modals/profile.html",
        {"app_version": "1.2.3", "app_environment": "test", "ambientes": [], "admins": []},
    )
    assert "Versão 1.2.3" in html
    assert "Ambiente test" in html
