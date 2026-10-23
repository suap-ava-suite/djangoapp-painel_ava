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
    assert ctx["ifrn25_analytics"] == {"gtag": "G-IFRN25", "clarity": "c25"}
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
