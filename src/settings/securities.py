# -*- coding: utf-8 -*-
from sc4py.env import env, env_as_bool, env_as_list

SECRET_KEY = env("DJANGO_SECRET_KEY", "#warning: changeme")
LOGIN_URL = env("DJANGO_LOGIN_URL", "/login/")
LOGIN_REDIRECT_URL = env("DJANGO_LOGIN_REDIRECT_URL", "/")
LOGOUT_REDIRECT_URL = env("DJANGO_LOGOUT_REDIRECT_URL", "/logout/")
AUTH_USER_MODEL = env("DJANGO_AUTH_USER_MODEL", "auth.User")
AUTHENTICATION_BACKENDS = env_as_list(
    "AUTHENTICATION_BACKENDS",
    ["django_suap_auth.profile.backends.SuapProfileAuthBackend", "django.contrib.auth.backends.ModelBackend"],
)
AUTH_PASSWORD_VALIDATORS = env_as_list("DJANGO_AUTH_PASSWORD_VALIDATORS", [])

# CSRF: atrás de proxy/HTTPS o Origin (ex.: https://ava.ifrn.edu.br) só é aceito se estiver em
# CSRF_TRUSTED_ORIGINS (ou se SECURE_PROXY_SSL_HEADER fizer o Django enxergar o esquema https).
CSRF_TRUSTED_ORIGINS = env_as_list("DJANGO_CSRF_TRUSTED_ORIGINS", [])
CSRF_COOKIE_DOMAIN = env("DJANGO_CSRF_COOKIE_DOMAIN", None)
CSRF_COOKIE_SECURE = env_as_bool("DJANGO_CSRF_COOKIE_SECURE", False)

oauth_base_url = env("OAUTH_BASE_URL", "https://suap.ifrn.edu.br")
SUAP_AUTH = {
    "CLIENT_ID": env("OAUTH_CLIENT_ID", "#warning: changeme"),
    "CLIENT_SECRET": env("OAUTH_CLIENT_SECRET", "#warning: changeme"),
    "REDIRECT_URI": env("OAUTH_REDIRECT_URI", "/auth/suap/callback/"),
    "BASE_URL": oauth_base_url,
    "SCOPES": ["identificacao", "email", "documentos_pessoais"],
    "USER_LOOKUP_FIELD": "username",
    "USER_ATTR_MAP": {
        "username": "identificacao",
        "nome_registro": "nome_registro",
        "nome_social": "nome_social",
        "nome_usual": "nome_usual",
        "first_name": "primeiro_nome",
        "last_name": "ultimo_nome",
        "email": "email_preferencial",
        "email_corporativo": "email",
        "email_google_classroom": "email_google_classroom",
        "email_academico": "email_academico",
        "email_secundario": "email_secundario",
        "foto": "foto",
        "tipo_usuario": "tipo_usuario",
    },
    "USER_DEFAULTS": {"is_active": True},
    "FIRST_USER_DEFAULTS": {"is_staff": True, "is_superuser": True},
    "BACKEND": "django_suap_auth.profile.backends.SuapProfileAuthBackend",
    "USER_JSON_FIELD": "suap_data",
    "USER_INFO_ENDPOINTS": [
        "/api/rh/eu/",
        {"endpoint": "/api/rh/meus-vinculos/", "namespace": "vinculos", "required": False},
    ],
}

SUAP_INTEGRADOR_KEY = env("SUAP_INTEGRADOR_KEY", "#warning: changeme")

SUAP = {
    "BASE_URL": env("SUAP_BASE_URL", "https://suap.ifrn.edu.br"),
}
