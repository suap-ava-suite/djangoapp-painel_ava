"""Diagnóstico de usuário para superusuários (personificação e autoinscrição).

Somente leitura: consulta o Painel e o endpoint ``get_diagnostico_usuario`` do tool_painelava de cada ambiente.
"""

import json
import logging
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from http.client import HTTPException
from typing import Any, Callable, Dict, List, Optional

import requests
from django.contrib.auth import get_user_model
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET
from django_rule_engine.explain_tree import explain_tree
from django_suap_auth.impersonation.helpers import is_impersonating

from painel.models import Ambiente
from painel.v1.services import (
    MOTIVO_OK,
    avaliar_autoinscricao,
    get_compiled_rule,
    get_json,
    get_user_context,
)

logger = logging.getLogger(__name__)

SERVICO_DIAGNOSTICO = "get_diagnostico_usuario"
SERVICO_DIARIOS = "get_diarios"
MOODLE_SERVICO_INEXISTENTE = "Serviço não existe"

STATUS_OK = "ok"
STATUS_SEM_CONTA = "sem_conta"
STATUS_ENDPOINT_INDISPONIVEL = "endpoint_indisponivel"
STATUS_ERRO = "erro"

# Campos do contexto que nunca aparecem no diagnóstico (dados pessoais sensíveis)
CAMPOS_SENSIVEIS = re.compile(r"cpf|rg|passaporte|email|e_mail|nascimento|telefone|filiacao|foto|endereco|senha")
CAMPOS_MATRICULA_EXIBIDOS = ("tipo", "campus", "curso", "modalidade", "nivel_ensino", "categoria", "cargo", "ativo")
MATRICULA_INDICE_ZERO = "outras_matriculas[0]"
STRING_LITERAL = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")


class MoodleIndisponivel(Exception):
    """Falha ao consultar o Moodle, com o status já classificado."""

    def __init__(self, status: str, mensagem: str, detalhe: str = ""):
        super().__init__(mensagem)
        self.status = status
        self.mensagem = mensagem
        self.detalhe = detalhe


def somente_superusuario(view: Callable) -> Callable:
    """Exige superusuário real (não o personificado) e recusa durante personificação."""

    @wraps(view)
    def _view(request: HttpRequest, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_superuser:
            return JsonResponse({"error": "Acesso restrito a superusuários."}, status=403)
        if is_impersonating(request):
            return JsonResponse({"error": "Encerre a personificação antes de diagnosticar."}, status=409)
        return view(request, *args, **kwargs)

    return _view


def _chamar_moodle(ava: Ambiente, servico: str, **params: Any) -> Any:
    """GET no tool_painelava sem enviar ao Sentry (uso pontual e manual por superusuário)."""
    querystring = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    url = f"{ava.moodle_base_api_url}/?{servico}&{querystring}"
    try:
        return get_json(url, headers={"Authentication": f"Token {ava.token}"})
    except HTTPException as e:
        status = getattr(e, "status", None)
        try:
            mensagem = json.loads(getattr(e, "body", "") or "")["error"]["message"]
        except ValueError, KeyError, TypeError:
            mensagem = ""
        if status == 404 and mensagem == MOODLE_SERVICO_INEXISTENTE:
            raise MoodleIndisponivel(STATUS_ENDPOINT_INDISPONIVEL, "Atualize o tool_painelava deste Moodle.")
        logger.warning(f"Diagnóstico: Moodle '{ava.nome}' {servico} respondeu HTTP {status}: {mensagem}")
        raise MoodleIndisponivel(STATUS_ERRO, f"O Moodle respondeu com erro HTTP {status}.", f"HTTP {status}")
    except requests.exceptions.Timeout as e:
        raise _falha_de_rede(ava, servico, e, "O Moodle não respondeu a tempo.")
    except requests.exceptions.ConnectionError as e:
        raise _falha_de_rede(ava, servico, e, "Não foi possível conectar ao Moodle.")
    except (requests.exceptions.RequestException, ValueError) as e:
        raise _falha_de_rede(ava, servico, e, "Resposta inválida do Moodle.")


def _falha_de_rede(ava: Ambiente, servico: str, erro: Exception, mensagem: str) -> MoodleIndisponivel:
    """O texto da exceção fica só no log do servidor; a resposta leva apenas o tipo da falha."""
    logger.warning(f"Diagnóstico: Moodle '{ava.nome}' {servico}: {type(erro).__name__}: {erro}")
    return MoodleIndisponivel(STATUS_ERRO, mensagem, type(erro).__name__)


def _ambiente_json(ava: Ambiente) -> dict:
    return {"id": ava.id, "nome": ava.nome, "cor_mestra": ava.cor_mestra}


def _em_paralelo(funcao: Callable[[Ambiente], dict]) -> List[dict]:
    """Só HTTP nas threads (mesmo cuidado de get_diarios); a ordem segue a dos ambientes."""
    ambientes = Ambiente.cached()
    if not ambientes:
        return []
    with ThreadPoolExecutor(max_workers=3) as executor:
        return list(executor.map(funcao, ambientes))


def _diagnostico_moodle(ava: Ambiente, username: str) -> dict:
    resultado = {"ambiente": _ambiente_json(ava), "status": STATUS_OK, "mensagem": "", "detalhe": "", "dados": None}
    try:
        dados = _chamar_moodle(ava, SERVICO_DIAGNOSTICO, username=username)
    except MoodleIndisponivel as e:
        resultado.update(status=e.status, mensagem=e.mensagem, detalhe=e.detalhe)
        return resultado
    if not isinstance(dados, dict):
        resultado.update(status=STATUS_ERRO, mensagem="Resposta inesperada do Moodle.")
        return resultado
    resultado["dados"] = dados
    if not dados.get("exists"):
        resultado["status"] = STATUS_SEM_CONTA
    return resultado


def _mascarar_email(email: Optional[str]) -> str:
    if not email or "@" not in email:
        return ""
    local, dominio = email.split("@", 1)
    return f"{local[:2]}***@{dominio}"


def _motivo_bloqueio_personificacao(alvo, operador) -> str:
    if alvo is None:
        return "inexistente"
    if alvo.pk == operador.pk:
        return "proprio_usuario"
    if alvo.is_superuser:
        return "alvo_superuser"
    if not alvo.is_active:
        return "inativo"
    return ""


def _matriculas_exibidas(contexto: dict) -> List[dict]:
    return [
        {"indice": i, **{campo: m.get(campo) for campo in CAMPOS_MATRICULA_EXIBIDOS}}
        for i, m in enumerate(contexto.get("outras_matriculas") or [])
        if isinstance(m, dict)
    ]


def _usuario_json(usuario, operador) -> dict:
    perfil = getattr(usuario, "suap_profile", None) if hasattr(usuario, "suap_profile") else None
    motivo = _motivo_bloqueio_personificacao(usuario, operador)
    return {
        "username": usuario.username,
        "nome": usuario.get_full_name() or getattr(perfil, "nome_usual", "") or "",
        "email": _mascarar_email(usuario.email),
        "is_superuser": usuario.is_superuser,
        "is_active": usuario.is_active,
        "last_login": usuario.last_login.isoformat() if usuario.last_login else None,
        "date_joined": usuario.date_joined.isoformat() if usuario.date_joined else None,
        "perfil": (
            {
                "tipo_usuario": perfil.tipo_usuario,
                "campus": perfil.campus,
                "curso": perfil.curso,
                "situacao": perfil.situacao,
            }
            if perfil
            else None
        ),
        "matriculas": _matriculas_exibidas(get_user_context(usuario)),
        "pode_personificar": not motivo,
        "motivo_bloqueio": motivo,
    }


def _buscar_usuario(username: str):
    return get_user_model().objects.filter(username__iexact=username).first()


@require_GET
@somente_superusuario
def diagnostico_usuario(request: HttpRequest, username: str) -> JsonResponse:
    username = username.strip().lower()
    usuario = _buscar_usuario(username)
    ambientes = []
    for item in _em_paralelo(lambda ava: _diagnostico_moodle(ava, username)):
        dados = item.pop("dados") or {}
        item["conta"] = dados.get("user")
        item["inscricoes"] = dados.get("enrolments")
        ambientes.append(item)

    return JsonResponse(
        {
            "username": username,
            "existe_no_painel": usuario is not None,
            "usuario": _usuario_json(usuario, request.user) if usuario else None,
            "pode_personificar": usuario is not None and not _motivo_bloqueio_personificacao(usuario, request.user),
            "motivo_bloqueio": _motivo_bloqueio_personificacao(usuario, request.user),
            "ambientes": ambientes,
        }
    )


# --- Autoinscrição ---------------------------------------------------------------------------------------------


def _indices_que_atenderiam(regra: str, contexto: dict) -> List[int]:
    """Se a regra usa ``outras_matriculas[0]``, em quais vínculos (índices) ela passaria."""
    if MATRICULA_INDICE_ZERO not in regra:
        return []
    indices = []
    for i in range(len(contexto.get("outras_matriculas") or [])):
        try:
            if get_compiled_rule(regra.replace(MATRICULA_INDICE_ZERO, f"outras_matriculas[{i}]")).matches(contexto):
                indices.append(i)
        except Exception:  # noqa: S112 - regra que não avalia com este índice: simplesmente não atende
            continue
    return indices


def _campos_da_regra(regra: str, contexto: dict) -> Dict[str, Any]:
    """Valores do contexto citados pela regra (exceto ``outras_matriculas`` e dados sensíveis)."""
    sem_literais = STRING_LITERAL.sub("''", regra)
    return {
        chave: valor
        for chave, valor in contexto.items()
        if chave != "outras_matriculas"
        and not CAMPOS_SENSIVEIS.search(chave)
        and re.search(rf"(?<![\w.]){re.escape(chave)}(?!\w)", sem_literais)
    }


def _situacao_inscricao(curso: dict) -> str:
    inscricao = curso.get("enrolment")
    if inscricao:
        if inscricao.get("status") == "active":
            return "ativa"
        if inscricao.get("expired"):
            return "expirada"
        return "suspensa"
    if curso.get("is_enrolled"):
        return "ativa"
    return "nenhuma"


def _rotulo_matricula(item) -> str:
    """Rótulo dos itens de outras_matriculas nos blocos: campus e curso, sem o identificador."""
    if not isinstance(item, dict):
        return ""
    curso = item.get("curso") or (item.get("detalhamento") or {}).get("curso") or ""
    return " · ".join(str(parte) for parte in (item.get("campus"), curso) if parte)


def _avaliar_curso(curso: dict, usuario, contexto: dict) -> dict:
    regra = (curso.get("restricoes_de_autoinscricao") or "").strip()
    atende, motivo, detalhe = avaliar_autoinscricao(regra, usuario, contexto if usuario else None)
    visivel = bool(curso.get("visible", True))
    arvore = None
    indices = []
    if usuario and regra and motivo != MOTIVO_OK:
        # Explicação nó a nó (django-rule-engine), desenhada em blocos no front (RuleBlocks)
        arvore = explain_tree(regra, contexto, sensitive=CAMPOS_SENSIVEIS, item_label=_rotulo_matricula)
        # Mensagem do erro da regra vem da explicação da django-rule-engine (já tratada por ela)
        detalhe = arvore.get("erro") or detalhe
        indices = _indices_que_atenderiam(regra, contexto)
    return {
        "courseid": curso.get("courseid") or curso.get("id"),
        "fullname": curso.get("fullname", ""),
        "shortname": curso.get("shortname", ""),
        "visivel": visivel,
        "regra": regra,
        "atende": atende,
        "motivo": motivo,
        "detalhe": detalhe,
        "arvore": arvore,
        "indices_que_atenderiam": indices,
        "campos_da_regra": _campos_da_regra(regra, contexto) if usuario else {},
        "inscricao": _situacao_inscricao(curso),
        "aparece_no_painel": bool(atende and visivel),
    }


def _cursos_autoinscricao(ava: Ambiente, username: str) -> dict:
    """Usa o endpoint de diagnóstico (inclui ocultos e status); sem ele, a vitrine de get_diarios."""
    item = _diagnostico_moodle(ava, username)
    if item["status"] in (STATUS_OK, STATUS_SEM_CONTA):
        item["fonte"] = SERVICO_DIAGNOSTICO
        item["cursos"] = (item.pop("dados") or {}).get("autoinscricoes") or []
        return item

    item.pop("dados", None)
    if item["status"] == STATUS_ENDPOINT_INDISPONIVEL:
        try:
            dados = _chamar_moodle(ava, SERVICO_DIARIOS, username=username, page_size=1)
            item["fonte"] = SERVICO_DIARIOS
            item["cursos"] = (dados.get("autoinscricoes") or []) if isinstance(dados, dict) else []
            return item
        except MoodleIndisponivel as e:
            item.update(status=e.status, mensagem=e.mensagem, detalhe=e.detalhe)
    item["fonte"] = None
    item["cursos"] = []
    return item


@require_GET
@somente_superusuario
def diagnostico_autoinscricao(request: HttpRequest, username: str) -> JsonResponse:
    username = username.strip().lower()
    usuario = _buscar_usuario(username)
    contexto = get_user_context(usuario) if usuario else {}

    # Avaliação na thread principal (ORM e cache de regras), só o HTTP vai para as threads
    ambientes = []
    for item in _em_paralelo(lambda ava: _cursos_autoinscricao(ava, username)):
        item["cursos"] = [_avaliar_curso(c, usuario, contexto) for c in item["cursos"] if isinstance(c, dict)]
        ambientes.append(item)

    return JsonResponse(
        {
            "username": username,
            "existe_no_painel": usuario is not None,
            "contexto": {
                "tipo_usuario": contexto.get("tipo_usuario"),
                "campus": contexto.get("campus"),
                "matriculas": _matriculas_exibidas(contexto),
            },
            "ambientes": ambientes,
        }
    )
