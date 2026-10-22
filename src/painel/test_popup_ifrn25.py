from types import SimpleNamespace

from django.template.loader import render_to_string

FOOT = "theme/ifrn25/frontpage/partials/foot.html"


def _popup(**kwargs):
    dados = dict(id=3, titulo="Aviso importante", url="https://exemplo.test/aviso", mensagem="<b>Leia</b> isto")
    dados.update(kwargs)
    return SimpleNamespace(**dados)


def test_foot_renderiza_popup_do_admin():
    html = render_to_string(FOOT, {"popup": _popup(), "last_startup": "x"})
    assert 'id="popup-admin"' in html
    assert 'data-popup-id="3"' in html
    assert 'data-popup-url="https://exemplo.test/aviso"' in html
    assert "Aviso importante" in html and "<b>Leia</b> isto" in html
    assert "Lembre-me depois" in html and "Acessar agora" in html
    assert "popup-admin.js" in html


def test_foot_sem_popup_nao_renderiza_o_modal():
    html = render_to_string(FOOT, {"popup": None, "last_startup": "x"})
    assert 'id="popup-admin"' not in html


def test_titulo_e_url_sao_escapados():
    html = render_to_string(
        FOOT, {"popup": _popup(titulo="<script>x</script>", url='x"><script>y</script>'), "last_startup": "x"}
    )
    assert "<script>x</script>" not in html
    assert "<script>y</script>" not in html
