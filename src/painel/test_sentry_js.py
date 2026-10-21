from django.template.loader import render_to_string

HEAD = "theme/ifrn25/frontpage/partials/head.html"


def _render_head(sentry_js):
    return render_to_string(HEAD, {"sentry_js": sentry_js, "last_startup": "x"})


def test_head_nao_carrega_sdk_sem_dsn():
    html = _render_head(None)
    assert "browser.sentry-cdn.com" not in html
    assert "sentry-js-config" not in html
    assert "sentry-init.js" in html


def test_head_carrega_sdk_com_dsn_proprio():
    html = _render_head({"dsn": "https://k@sentry.example/9", "environment": "t", "release": "1", "sampleRate": 1.0})
    assert "browser.sentry-cdn.com" in html
    assert 'id="sentry-js-config"' in html
    assert "https://k@sentry.example/9" in html
