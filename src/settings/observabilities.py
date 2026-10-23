# -*- coding: utf-8 -*-
from sc4py.env import env, env_as_bool, env_as_int

if env("GTAG_CODE") is not None:
    GTAG_CODE = env("GTAG_CODE")  # noqa

if env("CLARITY_CODE") is not None:
    CLARITY_CODE = env("CLARITY_CODE")  # noqa

# Analytics do theme_ifrn25: chaves próprias, independentes de GTAG_CODE/CLARITY_CODE (theme_ifrn23).
# Sem nenhuma das duas, o front-end não carrega GA/Clarity e `window.track()` é um no-op.
if env("IFRN25_GTAG_CODE") is not None or env("IFRN25_CLARITY_CODE") is not None:
    IFRN25_ANALYTICS = dict(  # noqa
        gtag=env("IFRN25_GTAG_CODE"),
        clarity=env("IFRN25_CLARITY_CODE"),
    )

if env("SENTRY_DNS") is not None:
    import logging

    import sentry_sdk
    from django.core.exceptions import DisallowedHost
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration, ignore_logger
    from sentry_sdk.integrations.redis import RedisIntegration

    from settings.project import APP_VERSION

    SENTRY_SETTINGS = dict(
        dsn=env("SENTRY_DNS"),
        integrations=[
            DjangoIntegration(),
            RedisIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        default_integrations=env_as_bool("SENTRY_DEFAULT_INTEGRATIONS", True),
        # Informe em porcentual, ou seja, 50 significa que 100% de erros serão reportados.
        sample_rate=env_as_int("SENTRY_SAMPLE_RATE", 100) / 100.0,
        # before_send=,
        # before_breadcrumb=,
        # Informe em porcentual, ou seja, 50 significa que 100% de erros serão reportados.
        traces_sample_rate=env_as_int("SENTRY_TRACES_SAMPLE_RATE", 100) / 100.0,
        # traces_sampler=
        # If you wish to associate users to errors (assuming you are using django.contrib.auth)
        # you may enable sending PII data.
        send_default_pii=env_as_bool("SENTRY_SEND_DEFAULT_PII", True),
        debug=env_as_bool("SENTRY_DEBUG", False),
        environment=env("SENTRY_ENVIRONMENT", "local"),
        max_breadcrumbs=env_as_int("SENTRY_MAX_BREADCRUMBS", 100),
        ignore_errors=[DisallowedHost],
        release=env("SENTRY_RELEASE", APP_VERSION),
        profiles_sample_rate=env_as_int("SENTRY_PROFILES_SAMPLE_RATE", 100) / 100.0,
        # attach_stacktrace=env('SENTRY_ATTACH_STACKTRACE', 'off'),
        # server_name=env('SENTRY_SERVER_NAME', 'off'),
        # in_app_include=env_as_list('SENTRY_IN_APP_INCLUDE', []),
        # in_app_exclude=env_as_list('SENTRY_IN_APP_EXCLUDE', []),
        # request_bodies=env_as_list('SENTRY_REQUEST_BODIES', []),
        # ca_certs=
        # request_bodies=
        # send_client_reports=
        # transport=,
        # shutdown_timeout=env_as_int('SENTRY_SHUTDOWN_TIMEOUT', 2),
    )
    sentry_sdk.init(**SENTRY_SETTINGS)
    ignore_logger("gunicorn.error")

# Sentry do JavaScript (navegador): DSN próprio, independente do SENTRY_DNS do Django.
# Sem SENTRY_JS_DSN, o front-end não carrega o SDK nem envia nada.
if env("SENTRY_JS_DSN") is not None:
    from settings.project import APP_VERSION as _SENTRY_JS_APP_VERSION

    SENTRY_JS = dict(  # noqa
        dsn=env("SENTRY_JS_DSN"),
        environment=env("SENTRY_JS_ENVIRONMENT", env("SENTRY_ENVIRONMENT", "local")),
        release=env("SENTRY_RELEASE", _SENTRY_JS_APP_VERSION),
        # Informe em porcentual, ou seja, 50 significa que 50% dos erros serão reportados.
        sampleRate=env_as_int("SENTRY_JS_SAMPLE_RATE", 100) / 100.0,
    )
