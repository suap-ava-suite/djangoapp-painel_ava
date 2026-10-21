from typing import Dict

from django.conf import settings
from django.http import HttpRequest
from django.urls import reverse
from django.utils.translation import gettext as _
from django_suap_auth.impersonation.helpers import get_active_user, is_impersonating

from painel import get_active_themes, get_installed_themes
from painel.models import Ambiente, Popup


def logged_user(request: HttpRequest):
    return get_active_user(request)


def popup(request: HttpRequest) -> Dict[str, Popup]:
    return {"popup": Popup.activePopup()}


def layout_settings(request: HttpRequest) -> dict:
    return {
        "logged_user": get_active_user(request),
        "show_vlibras": settings.SHOW_VLIBRAS,
        "show_userway": settings.SHOW_USERWAY,
        "userway_account": settings.USERWAY_ACCOUNT,
        "personificando": is_impersonating(request),
        "last_startup": settings.LAST_STARTUP,
        "app_version": settings.APP_VERSION,
        "hostname": settings.HOSTNAME,
        "gtag": settings.GTAG_CODE if hasattr(settings, "GTAG_CODE") else False,
        "clarity": settings.CLARITY_CODE if hasattr(settings, "CLARITY_CODE") else False,
        "sentry_js": getattr(settings, "SENTRY_JS", None),
        "ambientes": Ambiente.cached(),
        "admins": Ambiente.admins(),
        "installed_themes": get_installed_themes(),
        "active_themes": get_active_themes(),
    }


def top_menu(request: HttpRequest) -> dict:
    staff_menus = (
        [
            {
                "label": _("Admin"),
                "url": reverse("admin:index"),
            },
        ]
        if request.user.is_staff
        else []
    )

    return {
        "layout_navbar_top_menu": [
            {
                "label": _("Início"),
                "url": reverse("painel:dashboard"),
            },
        ]
        + staff_menus
    }
