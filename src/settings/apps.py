import datetime
import logging

from sc4py.env import env, env_as_bool, env_as_list

logger = logging.getLogger(__name__)

LAST_STARTUP = int(datetime.datetime.timestamp(datetime.datetime.now()) * 1000)

SHOW_USERWAY = env_as_bool("SHOW_USERWAY", True)
USERWAY_ACCOUNT = env("USERWAY_ACCOUNT", None)
SHOW_VLIBRAS = env_as_bool("SHOW_VLIBRAS", True)
SHOW_SUPPORT_FORM = env_as_bool("SHOW_SUPPORT_FORM", True)
SHOW_SUPPORT_CHAT = env_as_bool("SHOW_SUPPORT_CHAT", True)
HOSTNAME = env("HOSTNAME", "-")


# Apps
MY_APPS = env_as_list(
    "MY_APPS",
    [
        "theme_ifrn23",
        "theme_ifrn25",
        "backup",
        "painel",
        "painel.v1",
        "painel.v2",
        "health",
        "base",
        "mocks",
    ],
)

THIRD_APPS = env_as_list(
    "THIRD_APPS",
    [
        "import_export",
        "simple_history",
        "safedelete",
        "admin_auto_filters",
        "django_extensions",
        "sass_processor",
        "django_json_widget",
        "django_suap_auth",
        "django_suap_auth.profile",
        "django_suap_auth.impersonation",
    ],
)

try:
    import django_extensions  # noqa F401
except ImportError:
    logger.warning("django_extensions not installed, removing from INSTALLED_APPS")
    THIRD_APPS.remove("django_extensions")

try:
    import sass_processor  # noqa F401
except ImportError:
    logger.warning("sass_processor NOT INSTALLED, removing from INSTALLED_APPS")
    THIRD_APPS.remove("sass_processor")

DJANGO_APPS = env_as_list(
    "DJANGO_APPS",
    [
        "django.contrib.admin",
        "django.contrib.auth",
        "django.contrib.contenttypes",
        "django.contrib.sessions",
        "django.contrib.messages",
        "django.contrib.staticfiles",
    ],
)
# django_rule_engine fica fora das listas configuráveis por ambiente: o Diagnosticar usa os
# estáticos dela (rule_blocks.js/css), então precisa estar sempre instalada.
INSTALLED_APPS = MY_APPS + THIRD_APPS + DJANGO_APPS + ["dsgovbr", "django_rule_engine"]


SITE_ID = 1
