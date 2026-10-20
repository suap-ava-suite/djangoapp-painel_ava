import json
import logging

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django_suap_auth.profile.models import Perfil
from ninja import NinjaAPI

from backup.api import router as backup_router
from painel.context_processors import logged_user
from painel.v1.brokers import SuapBroker, TokenBroker
from painel.v1.services import (
    get_diarios,
    get_progresso,
    set_favourite_course,
    set_user_preference,
    set_visible_course,
)

api = NinjaAPI()
api.add_router("", backup_router)
logger = logging.getLogger(__name__)


@api.api_operation(["GET", "OPTIONS"], "/diarios/")
def diarios(
    request: HttpRequest,
    response: HttpResponse,
    semestre: str = None,
    situacao: str = None,
    ordenacao: str = None,
    disciplina: str = None,
    curso: str = None,
    ambiente: str = None,
    q: str = None,
    page: int = 1,
    page_size: int = 9,
):
    if request.method == "OPTIONS":
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response
    elif request.method == "GET":
        response["Access-Control-Allow-Origin"] = "*"
        return get_diarios(
            username=logged_user(request).username,
            semestre=semestre,
            situacao=situacao,
            disciplina=disciplina,
            curso=curso,
            ambiente=ambiente,
            q=q,
            page=page,
            page_size=page_size,
        )
    return api.create_response(request, {"message": "Método não permitido"}, status=405)


@api.api_operation(["GET", "OPTIONS"], "/progresso/")
def progresso(
    request: HttpRequest,
    response: HttpResponse,
    ambiente: str = None,
    cursos: str = None,
):
    if request.method == "OPTIONS":
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response
    elif request.method == "GET":
        response["Access-Control-Allow-Origin"] = "*"
        return get_progresso(
            username=logged_user(request).username,
            ambiente=ambiente,
            cursos=cursos,
        )
    return api.create_response(request, {"message": "Método não permitido"}, status=405)


@api.get("/atualizacoes_counts/")
def atualizacoes_counts(request: HttpRequest):
    return {
        "atualizacoes": [],
        "unread_notification_total": 0,
        "unread_conversations_total": 0,
    }


@api.api_operation(["GET", "OPTIONS"], "/set_favourite/")
def set_favourite(request: HttpRequest, response: HttpResponse, ava: str, courseid: int, favourite: int):
    if request.method == "OPTIONS":
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response
    elif request.method == "GET":
        response["Access-Control-Allow-Origin"] = "*"
        return set_favourite_course(logged_user(request).username, ava, courseid, favourite)

    return api.create_response(request, {"message": "Método não permitido"}, status=405)


@api.get("/set_visible/")
def set_visible(request: HttpRequest, ava: str, courseid: int, visible: int):
    return set_visible_course(logged_user(request).username, ava, courseid, visible)


@api.api_operation(["GET", "OPTIONS"], "/set_user_preference/")
def set_user_preference_endpoint(
    request: HttpRequest, response: HttpResponse, category: str, key: str, value: str, username: str = None
):
    if request.method == "OPTIONS":
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response
    elif request.method == "GET":
        response["Access-Control-Allow-Origin"] = "*"

        if username:
            User = get_user_model()
            user = User.objects.filter(username=username).first()
            if not user:
                return JsonResponse({"status": "error", "message": f"Usuário '{username}' não encontrado"}, status=404)
        else:
            user = logged_user(request)

        username = user.username

        try:
            # settings fica no Perfil (django_suap_auth), não em auth.User
            profile, _ = Perfil.objects.get_or_create(user=user)
            if profile.settings is None:
                profile.settings = {}

            if category not in profile.settings:
                profile.settings[category] = {}

            parsed_value = True if str(value).lower() == "true" else False if str(value).lower() == "false" else value

            profile.settings[category][key] = parsed_value
            profile.save(update_fields=["settings"])
        except Exception:
            logger.exception("Falha ao salvar preferência local '%s'", key)
            return JsonResponse(
                {"status": "error", "message": "Ocorreu um erro interno ao salvar a preferência."}, status=500
            )

        from painel.models import Ambiente

        ambientes = Ambiente.objects.all()
        erros = []

        name = f"theme_suap_{category}_{key}"

        for amb in ambientes:
            try:
                set_user_preference(username, ava=amb.nome, name=name, value=value)
            except Exception:
                erros.append(amb.nome)

        if erros:
            return JsonResponse(
                {
                    "status": "partial",
                    "message": f"Preferência salva localmente, mas falhou em {len(erros)} ambientes.",
                    "failed": erros,
                }
            )

        return JsonResponse({"status": "ok"})

    return api.create_response(request, {"message": "Método não permitido"}, status=405)


@api.api_operation(["POST", "OPTIONS"], "/authenticate/")
def authenticate(request: HttpRequest, response: HttpResponse) -> dict:
    if request.method == "OPTIONS":
        response["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response["Access-Control-Allow-Headers"] = "Authorization"
        response["Access-Control-Allow-Origin"] = "*"
        return response
    elif request.method == "POST":
        suap_broker = SuapBroker()
        response["Access-Control-Allow-Origin"] = "*"
        body = json.loads(request.body.decode("utf-8"))
        username = body.get("username")
        password = body.get("password")
        try:
            suap_broker.login(request=request, username=username, password=password)
        except ValidationError as e:
            error_response = api.create_response(
                request,
                {"message": e.message},
                status=401,
            )
            error_response["Access-Control-Allow-Origin"] = "*"
            return error_response
        user_data = suap_broker.get_user_data()
        expiration_days = 14
        token = TokenBroker().generate(username, expiration_days)
        return {
            "data": user_data,
            "token": token,
        }

    return api.create_response(request, {"message": "Método não permitido"}, status=405)


@api.api_operation(["POST", "OPTIONS"], "/verify/")
def verify(request: HttpRequest, response: HttpResponse) -> dict:
    if request.method == "OPTIONS":
        response["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response["Access-Control-Allow-Origin"] = "*"
        return response
    elif request.method == "POST":
        body = json.loads(request.body.decode("utf-8"))
        token = body.get("token")
        if not token:
            error_response = api.create_response(
                request,
                {"message": "token é obrigatório"},
                status=400,
            )
            error_response["Access-Control-Allow-Origin"] = "*"
            return error_response
        username = TokenBroker().verify(token=token)
        if username == "":
            error_response = api.create_response(
                request,
                {"message": "Token inválido"},
                status=401,
            )
            error_response["Access-Control-Allow-Origin"] = "*"
            return error_response
        return {"username": username}

    return api.create_response(request, {"message": "Método não permitido"}, status=405)
