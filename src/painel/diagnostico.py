"""Diagnóstico de usuário para superusuários (personificação e autoinscrição).

Somente leitura: consulta o Painel e o endpoint ``get_diagnostico_usuario`` do tool_painelava de cada ambiente.
"""

import json
import logging
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from functools import wraps
from http.client import HTTPException
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests
from django.contrib.auth import get_user_model
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET
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
NOT_IN = re.compile(r"not\s+in\b")
OPERADORES_SIMBOLICOS = ("==", "!=", ">=", "<=", "=~~", "!~~", "=~", "!~", ">", "<")
CHAVE_ENTRE_COLCHETES = re.compile(r"\[\s*'([^']*)'\s*\]|\[\s*\"([^\"]*)\"\s*\]")
COMPREENSAO_MATRICULAS = re.compile(
    r"^\$(?P<func>any|all)\(\s*\[(?P<expr>.*)\s+for\s+(?P<var>\w+)\s+in\s+(?P<iter>outras_matriculas)\s*\]\s*\)$", re.S
)
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
            mensagem = f"HTTP {status}"
        if status == 404 and mensagem == MOODLE_SERVICO_INEXISTENTE:
            raise MoodleIndisponivel(STATUS_ENDPOINT_INDISPONIVEL, "Atualize o tool_painelava deste Moodle.")
        raise MoodleIndisponivel(STATUS_ERRO, f"O Moodle respondeu com erro HTTP {status}.", mensagem)
    except requests.exceptions.Timeout as e:
        raise MoodleIndisponivel(STATUS_ERRO, "O Moodle não respondeu a tempo.", f"{type(e).__name__}: {e}")
    except requests.exceptions.ConnectionError as e:
        raise MoodleIndisponivel(STATUS_ERRO, "Não foi possível conectar ao Moodle.", f"{type(e).__name__}: {e}")
    except (requests.exceptions.RequestException, ValueError) as e:
        raise MoodleIndisponivel(STATUS_ERRO, "Resposta inválida do Moodle.", f"{type(e).__name__}: {e}")


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


def _dividir_condicoes(regra: str) -> List[str]:
    """Divide a regra nos ``and``/``or`` de nível superior, se todos forem do mesmo operador.

    Devolve ``[]`` quando não há divisão confiável (operadores misturados, uma só condição ou sintaxe inesperada).
    """
    texto = regra.strip()
    while texto.startswith("(") and texto.endswith(")") and _fecha_no_final(texto):
        texto = texto[1:-1].strip()

    partes, operadores, profundidade, inicio, i = [], set(), 0, 0, 0
    aspas = None
    while i < len(texto):
        c = texto[i]
        if aspas:
            if c == "\\":
                i += 2
                continue
            if c == aspas:
                aspas = None
        elif c in "'\"":
            aspas = c
        elif c in "([{":
            profundidade += 1
        elif c in ")]}":
            profundidade -= 1
        elif profundidade == 0:
            for op in ("and", "or"):
                fim = i + len(op)
                antes_ok = i == 0 or not (texto[i - 1].isalnum() or texto[i - 1] == "_")
                depois_ok = fim < len(texto) and not (texto[fim].isalnum() or texto[fim] == "_")
                if texto.startswith(op, i) and antes_ok and depois_ok:
                    partes.append(texto[inicio:i].strip())
                    operadores.add(op)
                    inicio = fim
                    i = fim - 1
                    break
        i += 1
    partes.append(texto[inicio:].strip())

    if len(operadores) != 1 or len(partes) < 2 or not all(partes):
        return []
    return partes


def _fecha_no_final(texto: str) -> bool:
    """O parêntese de abertura do início só fecha no último caractere?"""
    profundidade, aspas = 0, None
    for i, c in enumerate(texto):
        if aspas:
            if c == aspas:
                aspas = None
            continue
        if c in "'\"":
            aspas = c
        elif c == "(":
            profundidade += 1
        elif c == ")":
            profundidade -= 1
            if profundidade == 0 and i != len(texto) - 1:
                return False
    return True


def _avaliar_condicao(condicao: str, contexto: dict) -> dict:
    try:
        resultado, erro = bool(get_compiled_rule(condicao).matches(contexto)), ""
    except Exception as e:
        resultado, erro = None, f"{type(e).__name__}: {e}"
    return {
        "condicao": condicao,
        "resultado": resultado,
        "erro": erro,
        "detalhes": _detalhar_condicao(condicao, contexto),
    }


def _mascara_topo(texto: str) -> List[bool]:
    """Para cada posição: está fora de aspas e de parênteses/colchetes/chaves?"""
    mascara, profundidade, aspas, escapar = [], 0, None, False
    for c in texto:
        if aspas:
            mascara.append(False)
            if escapar:
                escapar = False
            elif c == "\\":
                escapar = True
            elif c == aspas:
                aspas = None
            continue
        if c in "'\"":
            aspas = c
        elif c in "([{":
            profundidade += 1
        elif c in ")]}":
            profundidade -= 1
        mascara.append(profundidade == 0 and not aspas and c not in ")]}")
    return mascara


def _palavra_em(texto: str, i: int, palavra: str) -> bool:
    fim = i + len(palavra)
    return (
        texto.startswith(palavra, i)
        and (i == 0 or not (texto[i - 1].isalnum() or texto[i - 1] == "_"))
        and (fim >= len(texto) or not (texto[fim].isalnum() or texto[fim] == "_"))
    )


def _dividir_comparacao(atomo: str) -> Optional[Tuple[str, str, str]]:
    """``campo op esperado`` no primeiro operador de comparação de nível superior; ``None`` se não houver."""
    mascara = _mascara_topo(atomo)
    for i in range(len(atomo)):
        if not mascara[i]:
            continue
        for op in OPERADORES_SIMBOLICOS:
            if atomo.startswith(op, i):
                return atomo[:i].strip(), op, atomo[i + len(op) :].strip()
        nao_em = NOT_IN.match(atomo, i) if _palavra_em(atomo, i, "not") else None
        if nao_em:
            return atomo[:i].strip(), "not in", atomo[nao_em.end() :].strip()
        if _palavra_em(atomo, i, "in") and i > 0:
            return atomo[:i].strip(), "in", atomo[i + 2 :].strip()
    return None


def _jsonavel(valor: Any) -> Any:
    if isinstance(valor, Decimal):
        return int(valor) if valor == valor.to_integral_value() else float(valor)
    if isinstance(valor, (list, tuple)):
        return [_jsonavel(v) for v in valor]
    if isinstance(valor, dict):
        return {str(k): _jsonavel(v) for k, v in valor.items()}
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    return str(valor)


def _valor_da_expressao(expressao: str, contexto: dict) -> Tuple[Any, str]:
    try:
        return _jsonavel(get_compiled_rule(expressao).evaluate(contexto)), ""
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _rotulo_campo(campo: str, variavel: str = "") -> str:
    """``m['detalhamento']['modalidade']`` vira ``detalhamento.modalidade``."""
    rotulo = CHAVE_ENTRE_COLCHETES.sub(lambda c: "." + (c.group(1) if c.group(1) is not None else c.group(2)), campo)
    if variavel and rotulo.startswith(variavel + "."):
        rotulo = rotulo[len(variavel) + 1 :]
    return rotulo


def _linha_comparacao(atomo: str, variavel: str = "") -> dict:
    comparacao = _dividir_comparacao(atomo)
    campo, operador, esperado = comparacao if comparacao else (atomo, "", "verdadeiro")
    return {
        "atomo": atomo,
        "campo": campo,
        "rotulo": _rotulo_campo(campo, variavel),
        "operador": operador,
        "esperado": esperado,
        "sensivel": bool(CAMPOS_SENSIVEIS.search(campo)),
    }


def _detalhar_condicao(condicao: str, contexto: dict) -> dict:
    """Campo, valor esperado e valor do usuário de cada comparação (por vínculo em ``$any``/``$all``)."""
    texto = condicao.strip()
    while texto.startswith("(") and texto.endswith(")") and _fecha_no_final(texto):
        texto = texto[1:-1].strip()

    compreensao = COMPREENSAO_MATRICULAS.match(texto)
    if compreensao:
        variavel, iteravel = compreensao.group("var"), compreensao.group("iter")
        linhas = []
        for atomo in _dividir_condicoes(compreensao.group("expr")) or [compreensao.group("expr").strip()]:
            linha = _linha_comparacao(atomo, variavel)
            valores, erro = (None, "")
            if not linha["sensivel"]:
                valores, erro = _valor_da_expressao(f"[{linha['campo']} for {variavel} in {iteravel}]", contexto)
            resultados, erro_resultado = _valor_da_expressao(f"[{atomo} for {variavel} in {iteravel}]", contexto)
            atendido = None
            if isinstance(resultados, list):
                atendido = any(resultados) if compreensao.group("func") == "any" else all(resultados)
            linha.update(valores=valores, resultados=resultados, atendido=atendido, erro=erro or erro_resultado)
            linhas.append(linha)
        return {"tipo": "por_vinculo", "funcao": compreensao.group("func"), "linhas": linhas}

    linhas = []
    for atomo in _dividir_condicoes(texto) or [texto]:
        linha = _linha_comparacao(atomo)
        valor, erro = (None, "") if linha["sensivel"] else _valor_da_expressao(linha["campo"], contexto)
        resultado, erro_resultado = _valor_da_expressao(atomo, contexto)
        atendido = resultado if isinstance(resultado, bool) else None
        linha.update(valor=valor, resultado=resultado, atendido=atendido, erro=erro or erro_resultado)
        linhas.append(linha)
    return {"tipo": "simples", "linhas": linhas}


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


def _avaliar_curso(curso: dict, usuario, contexto: dict) -> dict:
    regra = (curso.get("restricoes_de_autoinscricao") or "").strip()
    atende, motivo, detalhe = avaliar_autoinscricao(regra, usuario, contexto if usuario else None)
    visivel = bool(curso.get("visible", True))
    condicoes = []
    indices = []
    if usuario and regra and motivo != MOTIVO_OK:
        condicoes = [_avaliar_condicao(c, contexto) for c in _dividir_condicoes(regra) or [regra]]
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
        "condicoes": condicoes,
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
