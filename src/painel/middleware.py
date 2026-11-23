import logging

import psycopg
import psycopg_pool
from django.conf import settings
from django.contrib import auth
from django.core.exceptions import DisallowedHost, SuspiciousOperation
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.utils.deprecation import MiddlewareMixin

from painel.models import Ambiente
from painel.v1.brokers import TokenBroker

logger = logging.getLogger(__name__)

token_broker = TokenBroker()


class GoToHTTPSMiddleware(MiddlewareMixin):
    """
    Force all requests to use HTTPs when behind a reverse proxy.

    .. note::
        ``settings.GO_TO_HTTPS`` needs to be True.
        The RP need to inform HTTP_X_FORWARDED_PROTO and HTTP_X_FORWARDED_HOST.
        If RP dont inform HTTP_X_FORWARDED_PROTO http will be assumed.
    """

    def process_request(self, request):
        if not getattr(settings, "GO_TO_HTTPS", False):
            return None

        meta = request.META
        proto = meta.get("HTTP_X_FORWARDED_PROTO", "http")

        if proto == "https":
            return None

        host = meta["HTTP_X_FORWARDED_HOST"] or request.get_host()
        url = "https://%s%s" % (host, request.get_full_path())

        return HttpResponseRedirect(url)


class AuthMobileUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = getattr(request, "path", "")
        method = getattr(request, "method", "")
        headers = getattr(request, "headers", {}) or {}
        session_key = getattr(getattr(request, "session", None), "session_key", None)

        dont_have_session = session_key is None
        is_to_api = "/api/v1/" in path
        is_not_to_auth = "/authenticate/" not in path and "/verify/" not in path
        is_not_options_method = method != "OPTIONS"

        # Só roda para requests externos à API
        if dont_have_session and is_to_api and is_not_to_auth and is_not_options_method:
            auth_header = headers.get("Authorization", "").split(" ")
            if len(auth_header) != 2 or not auth_header[1]:
                return JsonResponse(
                    {"error": {"message": "Invalid or not present authentication token", "code": 428}}, status=428
                )

            token = auth_header[1]

            # 1 Verifica se o token pertence a um Ambiente
            ambiente = Ambiente.objects.filter(token=token).first()
            if ambiente:
                request.ambiente = ambiente
                return self.get_response(request)

            # 2 Caso contrário, tenta autenticar como usuário
            try:
                username = token_broker.verify(token=token)
            except Exception:
                return JsonResponse({"error": {"message": "Invalid authentication token", "code": 403}}, status=403)

            if not username:
                return JsonResponse({"error": {"message": "Invalid authentication token", "code": 403}}, status=403)

            from django.contrib.auth import get_user_model

            User = get_user_model()
            user = User.objects.filter(username=username).first()
            if not user:
                return JsonResponse({"error": {"message": "Usuário não encontrado", "code": 404}}, status=404)

            auth.login(request, user)
            response = self.get_response(request)
            auth.logout(request)
            return response

        # requests locais ou com sessão seguem o fluxo normal
        return self.get_response(request)


class ExceptionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        except Exception as e:
            if isinstance(e, psycopg_pool.PoolTimeout):
                return HttpResponse("Erro de conexão com o banco!", status=500)
            if isinstance(e, psycopg.errors.Error):
                return HttpResponse("Erro de conexão com o banco!", status=500)
            if isinstance(e, DisallowedHost):
                from django.template import loader

                try:
                    template = loader.get_template("400_disallowed_host.html")
                    content = template.render()
                    return HttpResponse(content, status=400)
                except Exception:
                    return HttpResponse("Acesso não permitido (Disallowed Host)", status=400)
            if isinstance(e, SuspiciousOperation):
                raise
            logger.exception("Unhandled exception in ExceptionMiddleware")
            return HttpResponse("Erro interno do servidor!", status=500)


class XForwardedForMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if "HTTP_X_FORWARDED_FOR" in request.META:
            request.META["REMOTE_ADDR"] = request.META["HTTP_X_FORWARDED_FOR"].split(",")[0].strip()
        return None
