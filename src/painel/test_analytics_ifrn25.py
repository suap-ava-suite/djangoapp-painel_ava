import shutil
import subprocess  # noqa: S404
from pathlib import Path

import pytest
from django.template.loader import render_to_string

HEAD = "theme/ifrn25/frontpage/partials/head.html"
TESTES_JS = Path(__file__).parent / "tests_js"


def _render_head(analytics):
    return render_to_string(HEAD, {"ifrn25_analytics": analytics, "last_startup": "x"})


def test_head_sem_chaves_nao_expoe_config_mas_carrega_helper():
    html = _render_head(None)
    assert "analytics-config" not in html
    assert "theme/ifrn25/js/analytics.js" in html


def test_head_com_chaves_proprias_expoe_config():
    html = _render_head({"gtag": "G-IFRN25", "clarity": "clarity25"})
    assert 'id="analytics-config"' in html
    assert "G-IFRN25" in html
    assert "clarity25" in html
    assert html.index("analytics-config") < html.index("analytics.js")


def test_helper_vem_antes_do_sentry_e_do_app():
    html = _render_head(None)
    assert html.index("analytics.js") < html.index("sentry-init.js")


def test_context_processor_usa_chaves_do_ifrn25(settings, rf):
    from painel.context_processors import layout_settings

    settings.IFRN25_ANALYTICS = {"gtag": "G-IFRN25", "clarity": "c25"}
    settings.CLARITY_CODE = "outro-tema"
    request = rf.get("/")
    request.user = type("U", (), {"is_authenticated": False, "is_anonymous": True})()
    ctx = layout_settings(request)
    assert ctx["ifrn25_analytics"] == {"gtag": "G-IFRN25", "clarity": "c25", "app_version": settings.APP_VERSION}
    assert ctx["clarity"] == "outro-tema"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js não instalado")
def test_suite_node_do_analytics_passa():
    resultado = subprocess.run(  # noqa: S603
        [shutil.which("node"), "--test", str(TESTES_JS / "analytics.test.js")],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr


EVENTOS_PLANEJADOS = [
    "sidebar_toggle",
    "modal_abrir",
    "aba_selecionar",
    "menu_posicao_alterar",
    "curso_abrir",
    "curso_detalhes_ver",
    "curso_favoritar",
    "curso_visibilidade_alterar",
    "curso_visibilidade_confirmar",
    "progresso_carregar_falha",
    "filtro_aplicar",
    "filtro_limpar",
    "filtro_remover",
    "busca_sem_resultado",
    "carregamento_lento",
    "matricula_iniciar",
    "matricula_sucesso",
    "matricula_falha",
    "matricula_cancelar_confirmar",
    "matricula_cancelar_sucesso",
    "a11y_preferencia_alterar",
    "a11y_zoom_alterar",
    "a11y_contraste_alterar",
    "ajuda_link_clicar",
    "perfil_link_clicar",
    "tema_trocar",
    "ambiente_acessar",
    "logout",
    "tour_iniciar",
    "tour_passo",
    "tour_concluir",
    "popup_exibir",
    "popup_fechar",
    "aviso_modal_exibir",
    "erro_rede_dialogo_exibir",
]


def test_todos_os_eventos_do_plano_estao_instrumentados_no_tema():
    raiz = Path(__file__).parent.parent / "theme_ifrn25"
    fontes = "".join(
        arquivo.read_text(encoding="utf-8")
        for arquivo in raiz.rglob("*")
        if arquivo.suffix in {".js", ".html"} and arquivo.name != "analytics.js"
    )
    faltando = [e for e in EVENTOS_PLANEJADOS if e not in fontes]
    assert not faltando, f"Eventos sem instrumentação: {faltando}"


def test_ifrn23_nao_foi_instrumentado():
    raiz = Path(__file__).parent.parent / "theme_ifrn23"
    for arquivo in raiz.rglob("*.html"):
        assert "data-track" not in arquivo.read_text(encoding="utf-8"), arquivo
