import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from painel.context_processors import logged_user
from painel.models import Ambiente, ConfiguracaoAba, Situacao, Theme
from painel.v1.services import get_json_api

logger = logging.getLogger(__name__)


def get_user_profile(user):
    profile = getattr(user, "suap_profile", None)
    return profile if profile is not None else user


def __get_theme_prefix(request: HttpRequest) -> str:
    profile = get_user_profile(request.user)
    theme_selected = getattr(profile, "theme_selected", "ifrn25")
    instance = Theme.objects.filter(nome=theme_selected, active=True).first()
    if instance is None:
        return "theme/ifrn25"

    return f"theme/{theme_selected}"


@login_required
@ensure_csrf_cookie
def dashboard(request: HttpRequest) -> HttpResponse:
    abas_db = ConfiguracaoAba.objects.all()

    config_abas = {}
    for aba in abas_db:
        config_abas[aba.chave] = {
            "desktop": aba.nome_desktop,
            "mobile": aba.nome_mobile,
            "order": aba.ordem,
            "sempreVisivel": aba.sempre_visivel,
        }

    # 3. Entrega a página com o JSON injetado
    return render(
        request,
        __get_theme_prefix(request) + "/frontpage/index.html",
        {
            "enable_filters": True,
            "config_abas_json": json.dumps(config_abas),
        },
    )


@login_required
def change_theme(request: HttpRequest, theme: str) -> HttpResponse:
    instance = Theme.objects.filter(nome=theme, active=True).first()
    if instance is None:
        return redirect("painel:dashboard")

    profile = get_user_profile(request.user)
    if profile.settings is None:
        profile.settings = {}
    if "theme" not in profile.settings:
        profile.settings["theme"] = {}
    profile.settings["theme"]["selected"] = theme
    profile.save()
    return redirect("painel:dashboard")


@login_required
@require_POST
def change_menu_position(request: HttpRequest) -> JsonResponse:
    position = request.POST.get("position")
    if position not in ("top", "bottom"):
        return JsonResponse({"error": "Valor inválido"}, status=400)

    profile = get_user_profile(request.user)
    if profile.settings is None:
        profile.settings = {}
    profile.settings["menu_position"] = position
    profile.save()
    return JsonResponse({"status": "ok", "position": position})


@login_required
def checkgrades(request: HttpRequest, id_ambiente: int, id_diario: int) -> HttpResponse:
    ambiente = get_object_or_404(Ambiente, pk=id_ambiente)
    resposta = (
        get_json_api(
            ambiente,
            "get_diarios",
            **{"username": logged_user(request).username, "q": f"#{id_diario}", "situacao": Situacao.ALL},
        )
        or {}
    )
    diario = resposta["diarios"][0] if len(resposta.get("diarios", [])) == 1 else None
    if diario is None:
        raise Exception("Diário não encontrado")
    parts = diario.get("idnumber", "").split("#")
    diario["id_diario"] = parts[1] if len(parts) == 2 else None
    alunos = get_json_api(ambiente, "sync_down_grades", **{"diario_id": id_diario}) or []
    etapas = {}
    for grade in alunos:
        if grade["notas"]:
            for nota in grade["notas"].keys():
                etapas[nota] = nota
    context = {"diario": diario, "alunos": alunos, "etapas": etapas.keys()}
    return render(request, __get_theme_prefix(request) + "/diario/checkgrades.html", context=context)


@login_required
def completed_tour(request: HttpRequest) -> HttpResponse:
    profile = get_user_profile(request.user)
    if profile.settings is None:
        profile.settings = {}
    if "tour" not in profile.settings:
        profile.settings["tour"] = {}
    profile.settings["tour"]["completed"] = True
    profile.save()
    return JsonResponse({"status": "ok"})


@login_required
def get_tour_status(request: HttpRequest) -> HttpResponse:
    profile = get_user_profile(request.user)

    if profile.settings and "tour" in profile.settings and "completed" in profile.settings["tour"]:
        completed = profile.settings["tour"]["completed"]
    else:
        completed = False

    return JsonResponse({"completed_tour": completed})


@ensure_csrf_cookie
def curso_detalhes(request, id_ambiente, id_curso):
    ambiente = get_object_or_404(Ambiente, id=id_ambiente)

    # Usuário ativo: o personificado, quando um superusuário personifica alguém
    usuario = logged_user(request)
    username = usuario.username if usuario and usuario.is_authenticated else ""

    curso_data = get_json_api(ambiente, "get_course_info", courseid=id_curso, username=username) or {}

    curso_nome = curso_data.get("fullname", "Detalhes do Curso")
    curso_summary = curso_data.get("summary", "Nenhuma descrição disponível para este curso.")
    curso_is_enrolled = curso_data.get("is_enrolled", False)
    curso_docentes = curso_data.get("docentes", [])
    curso_carga_horaria = curso_data.get("carga_horaria", "")

    context = {
        "id_ambiente": id_ambiente,
        "id_curso": id_curso,
        "ambiente_nome": ambiente.nome,
        "moodle_url": ambiente.moodle_base_url,
        "enable_filters": False,
        "curso_nome": curso_nome,
        "curso_summary": curso_summary,
        "is_enrolled": curso_is_enrolled,
        "docentes": curso_docentes,
        "carga_horaria": curso_carga_horaria,
    }
    return render(request, "theme/ifrn25/frontpage/partials/curso_detalhes.html", context)


@login_required
@require_POST
def enrol_course(request, id_ambiente, id_curso):
    ambiente = get_object_or_404(Ambiente, id=id_ambiente)
    # Inscreve o usuário ativo: o personificado, quando um superusuário personifica alguém
    user = logged_user(request)
    profile = get_user_profile(user)
    username = user.username

    primeiro_nome = user.first_name
    ultimo_nome = user.last_name

    if not primeiro_nome:
        # Fallback seguro: se tudo for nulo, a string "Aluno SUAP" salva o .split() de quebrar
        nome_completo = getattr(profile, "nome_usual", None) or getattr(profile, "nome_registro", None) or "Aluno SUAP"
        partes_nome = nome_completo.split()
        primeiro_nome = partes_nome[0]
        ultimo_nome = " ".join(partes_nome[1:]) if len(partes_nome) > 1 else "SUAP"

    # Garante um e-mail válido
    email = user.email or getattr(profile, "email_preferencial", None) or f"{username}@sememail.ifrn.edu.br"

    campus_sigla_usuario = getattr(profile, "campus_sigla", "")

    # Faz a requisição enviando os dados de provisionamento JIT
    response = get_json_api(
        ambiente,
        "enrol_course",
        courseid=id_curso,
        username=username,
        firstname=primeiro_nome,
        lastname=ultimo_nome,
        email=email,
        campus=campus_sigla_usuario,
    )

    if not response:
        return JsonResponse({"status": "error", "message": "Falha de comunicação com o AVA."}, status=500)

    return JsonResponse(response)


@login_required
@require_POST
def unenrol_course(request, id_ambiente, id_curso):
    ambiente = get_object_or_404(Ambiente, id=id_ambiente)
    username = logged_user(request).username

    response = get_json_api(ambiente, "suspend_enrol", courseid=id_curso, username=username)

    if not response:
        return JsonResponse(
            {"status": "error", "message": "Falha de comunicação com o AVA ao tentar suspender a matrícula."},
            status=500,
        )

    return JsonResponse(response)
