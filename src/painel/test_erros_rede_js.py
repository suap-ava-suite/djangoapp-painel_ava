import shutil
import subprocess  # noqa: S404
from pathlib import Path

import pytest
from django.template.loader import render_to_string

HEAD = "theme/ifrn25/frontpage/partials/head.html"
TESTES_JS = Path(__file__).parent / "tests_js"


def test_head_carrega_helper_de_erros_de_rede_antes_do_app():
    html = render_to_string(HEAD, {"sentry_js": None, "last_startup": "x"})
    assert "theme/ifrn25/js/erros-rede.js" in html
    assert html.index("sentry-init.js") < html.index("erros-rede.js")


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js não instalado")
def test_suite_node_dos_erros_de_rede_passa():
    resultado = subprocess.run(  # noqa: S603
        [shutil.which("node"), "--test", str(TESTES_JS / "erros-rede.test.js")],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr


def test_foot_inclui_dialogo_de_aviso_com_todos_os_ids_usados_pelo_js():
    html = render_to_string("theme/ifrn25/frontpage/partials/foot.html", {"last_startup": "x"})
    for id_ in (
        "aviso-modal",
        "aviso-modal-title",
        "aviso-modal-message",
        "aviso-modal-codigo",
        "aviso-modal-codigo-valor",
        "aviso-modal-copiar",
        "aviso-modal-fechar",
    ):
        assert f'id="{id_}"' in html
