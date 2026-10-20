import concurrent
import json
import logging
import re
import time
import urllib.parse
from functools import lru_cache
from http.client import HTTPException
from typing import Any, Dict, List, Union

import requests
import rule_engine
import sentry_sdk
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.shortcuts import get_object_or_404
from django.urls import reverse

from backup.models import ArquivoBackup
from painel.models import Ambiente, Curso

logger = logging.getLogger(__name__)

MENSAGEM_REGRA_NAO_AVALIADA = "Regra de autoinscrição não avaliada"
MENSAGEM_FALHA_MOODLE = "Falha de comunicação com o Moodle"
MOODLE_USUARIO_NAO_ENCONTRADO = "Usuário não encontrado."

HTTP_CONNECTION_RETRIES = 1
HTTP_RETRY_BACKOFF = 0.3


CODIGO_DIARIO_REGEX = re.compile("^(\\d\\d\\d\\d\\d)\\.(\\d*)\\.(\\d*)\\.(.*)\\.(\\w*\\.\\d*)(#\\d*)?$")
CODIGO_DIARIO_ANTIGO_ELEMENTS_COUNT = 5
CODIGO_DIARIO_NOVO_ELEMENTS_COUNT = 6
CODIGO_DIARIO_SEMESTRE_INDEX = 0
CODIGO_DIARIO_PERIODO_INDEX = 1
CODIGO_DIARIO_CURSO_INDEX = 2
CODIGO_DIARIO_TURMA_INDEX = 3
CODIGO_DIARIO_DISCIPLINA_INDEX = 4
CODIGO_DIARIO_ID_DIARIO_INDEX = 5

CODIGO_COORDENACAO_REGEX = re.compile(r"^(\w*)\.(\d+)(.*)?$")
CODIGO_COORDENACAO_ELEMENTS_COUNT = 3
CODIGO_COORDENACAO_CAMPUS_INDEX = 0
CODIGO_COORDENACAO_CURSO_INDEX = 1
CODIGO_COORDENACAO_SUFIXO_INDEX = 2

CODIGO_PRATICA_REGEX = re.compile("^(\\d\\d\\d\\d\\d)\\.(\\d*)\\.(\\d*)\\.(.*)\\.(\\d{11,14}\\d*)$")
CODIGO_PRATICA_ELEMENTS_COUNT = 5
CODIGO_PRATICA_SUFIXO_INDEX = 4

CHANGE_URL = re.compile("/course/view.php\\?")


@lru_cache(maxsize=2048)
def get_compiled_rule(regra: str):
    return rule_engine.Rule(regra)


def get_user_context(usuario_db) -> dict:
    profile = getattr(usuario_db, "suap_profile", None)
    if profile is None:
        # Fallback para compatibilidade caso usuario_db seja um modelo legado
        if hasattr(usuario_db, "contexto"):
            return usuario_db.contexto
        return {}

    # DadosBrutos e Vinculo se ligam ao usuário (suap_raw_data / suap_vinculos), não ao Perfil
    raw_data_obj = getattr(usuario_db, "suap_raw_data", None)
    last_json = dict(getattr(raw_data_obj, "data", None) or {}) if raw_data_obj else {}

    matriculas = []
    if hasattr(usuario_db, "suap_vinculos"):
        for v in usuario_db.suap_vinculos.all():
            det = dict(v.detalhamento or {})
            det.setdefault("nivel_ensino", v.nivel_ensino or "")
            det.setdefault("modalidade", v.modalidade or "")
            det.setdefault("curso", v.curso or "")
            if det.get("ativo") is None:
                det["ativo"] = v.ativo if v.ativo is not None else False

            matriculas.append(
                {
                    "identificador": v.identificador or "",
                    "tipo": v.tipo or "",
                    "campus": v.campus or "",
                    "cargo": v.cargo or "",
                    "categoria": v.categoria or "",
                    "modalidade": v.modalidade or "",
                    "nivel_ensino": v.nivel_ensino or "",
                    "curso": v.curso or "",
                    "ativo": v.ativo if v.ativo is not None else False,
                    "estrangeiro": v.estrangeiro or False,
                    "detalhamento": det,
                }
            )

    last_json["outras_matriculas"] = matriculas
    return last_json


def check_autoinscricao(regra: str, usuario_db, contexto: Union[dict, None] = None) -> bool:
    if not regra or not str(regra).strip() or not usuario_db:
        return False

    try:
        rule = get_compiled_rule(regra)
    except Exception as e:
        logger.error(f"Regra inválida: {e}. {regra}")
        return False

    if contexto is None:
        contexto = get_user_context(usuario_db)
    try:
        resultado = rule.matches(contexto)
        username = getattr(usuario_db, "username", "unknown")
        sucesso = "PASSOU" if resultado else "FOI BLOQUEADO"
        logger.debug(f'Usuário {username} {sucesso} na regra "{regra}". Contexto: {contexto}')
        return resultado
    except Exception as e:
        username = getattr(usuario_db, "username", "unknown")
        # Mensagem fixa e fingerprint único: todos os eventos caem numa só issue do Sentry
        logger.warning(f'Erro ao avaliar para {username} a regra "{regra}". Erro: {e}. Contexto: {contexto}')
        with sentry_sdk.new_scope() as scope:
            scope.fingerprint = ["autoinscricao-regra-nao-avaliada"]
            scope.set_context(
                "autoinscricao", {"username": username, "regra": regra, "erro": str(e), "contexto": contexto}
            )
            sentry_sdk.capture_message(MENSAGEM_REGRA_NAO_AVALIADA, level="info")
        return False


def _filtrar_autoinscricoes(autoinscricoes: list, usuario_db) -> list:
    if not autoinscricoes or not usuario_db:
        return []

    # Contexto montado uma única vez (evita N+1 em suap_vinculos a cada curso)
    contexto = get_user_context(usuario_db)
    return [
        c for c in autoinscricoes if check_autoinscricao(c.get("restricoes_de_autoinscricao", ""), usuario_db, contexto)
    ]


def _get_with_retry(url, headers, **kwargs):
    """Uma nova tentativa para falhas de conexão (timeout de conexão, DNS e TLS), que costumam ser transitórias."""
    for _ in range(HTTP_CONNECTION_RETRIES):
        try:
            return requests.get(url, headers=headers, timeout=settings.DEFAULT_HTTP_TIMEOUT, **kwargs)
        except requests.exceptions.ConnectionError as e:
            logger.info(f"Falha de conexão em {url}, nova tentativa em {HTTP_RETRY_BACKOFF}s: {e}")
            time.sleep(HTTP_RETRY_BACKOFF)
    # Última tentativa: a exceção, se houver, sobe para o chamador
    return requests.get(url, headers=headers, timeout=settings.DEFAULT_HTTP_TIMEOUT, **kwargs)


def requests_get(url, headers={}, encoding="utf-8", decode=True, **kwargs):
    response = _get_with_retry(url, headers, **kwargs)
    byte_array_content = response.content
    content = byte_array_content.decode(encoding) if decode and encoding is not None else byte_array_content
    if response.ok:
        return content
    else:
        split_url = urllib.parse.urlsplit(url)
        safe_url = f"{split_url.scheme}://{split_url.netloc}{split_url.path}"
        # 404 do plugin é decidido em get_json_api (usuário ausente é esperado); não gera evento aqui
        log = logger.info if response.status_code == 404 else logger.error
        log(f"Error fetching {safe_url}: {response.status_code} - {response.reason}")
        exc = HTTPException("%s - %s" % (response.status_code, response.reason))
        exc.status = response.status_code
        exc.reason = response.reason
        exc.headers = response.headers
        exc.url = url
        exc.body = content
        raise exc


def get_json(url, headers={}, encoding="utf-8", json_kwargs=None, **kwargs):
    content = requests_get(url, headers=headers, encoding=encoding, **kwargs)
    return json.loads(content, **(json_kwargs or {}))


def get_json_api(ava: Ambiente, service: str, **params: dict):
    if params is not None:
        querystring = "&".join([f"{k}={v}" for k, v in params.items() if v is not None])
    else:
        querystring = ""
    url = f"{ava.moodle_base_api_url}/?{service}&{querystring}"
    try:
        return get_json(url, headers={"Authentication": f"Token {ava.token}"})
    except HTTPException as e:
        if _usuario_nao_encontrado(e):
            logger.info(f"Moodle '{ava.nome}': usuário não encontrado em {service}")
            return None
        _registrar_falha_moodle(ava, service, url, e)
        return None
    except (requests.exceptions.RequestException, ValueError) as e:
        _registrar_falha_moodle(ava, service, url, e)
        return None


def _usuario_nao_encontrado(exc: HTTPException) -> bool:
    """404 do tool_painelava com 'Usuário não encontrado.' (o 404 'Serviço não existe' continua sendo falha)."""
    if getattr(exc, "status", None) != 404:
        return False
    try:
        mensagem = json.loads(getattr(exc, "body", "") or "")["error"]["message"]
    except ValueError, KeyError, TypeError:
        return False
    return mensagem == MOODLE_USUARIO_NAO_ENCONTRADO


def _registrar_falha_moodle(ava: Ambiente, service: str, url: str, exc: Exception) -> None:
    """Falha transitória/de resposta do Moodle: warning e uma única issue no Sentry (fingerprint fixo)."""
    logger.warning(f"⚠️ Falha ao acessar o Moodle '{ava.nome}' em {url}: {type(exc).__name__}: {exc}")
    with sentry_sdk.new_scope() as scope:
        scope.fingerprint = ["moodle-falha-de-comunicacao"]
        scope.set_context(
            "moodle", {"ambiente": ava.nome, "servico": service, "url": url, "erro": f"{type(exc).__name__}: {exc}"}
        )
        sentry_sdk.capture_message(MENSAGEM_FALHA_MOODLE, level="warning")


def get_diarios(
    username: str,
    semestre: str = None,
    situacao: str = None,
    disciplina: str = None,
    curso: str = None,
    ambiente: str = None,
    q: str = None,
    page: int = 1,
    page_size: int = 21,
) -> dict:

    CHAVES_ESTATICAS = ["semestres", "disciplinas", "cursos", "ambientes", "autoinscricoes", "reutilizaveis"]

    @lru_cache(maxsize=1024)
    def get_curso_cached(co_curso):
        cache_key = f"curso:{co_curso}"
        curso_bd = cache.get(cache_key)
        if not curso_bd:
            curso_bd = Curso.objects.filter(codigo=co_curso).first()
            if curso_bd:
                cache.set(cache_key, curso_bd, timeout=86400)
        return curso_bd

    User = get_user_model()
    usuario_db = User.objects.filter(username=username).first()

    def _merge_course(diario: dict, ambiente: dict):
        co_curso = diario.get("curso_codigo")
        turma_nova = diario.get("turma_ano_periodo")
        componente_novo = diario.get("disciplina_sigla")
        id_diario_novo = diario.get("diario_id")

        codigo = diario.get("shortname", "")
        diario_re = CODIGO_DIARIO_REGEX.findall(codigo)
        coordenacao_re = CODIGO_COORDENACAO_REGEX.findall(codigo)
        pratica_re = CODIGO_PRATICA_REGEX.findall(codigo)

        if not co_curso:
            if diario_re and len(diario_re[0]) > CODIGO_DIARIO_CURSO_INDEX:
                co_curso = diario_re[0][CODIGO_DIARIO_CURSO_INDEX]
            elif pratica_re and len(pratica_re[0]) > CODIGO_DIARIO_CURSO_INDEX:
                co_curso = pratica_re[0][CODIGO_DIARIO_CURSO_INDEX]
            elif coordenacao_re and len(coordenacao_re[0]) > CODIGO_COORDENACAO_CURSO_INDEX:
                co_curso = coordenacao_re[0][CODIGO_COORDENACAO_CURSO_INDEX]

        if co_curso:
            curso_bd = get_curso_cached(co_curso)
            if curso_bd is not None:
                diario["curso"] = {"codigo": curso_bd.codigo, "nome": curso_bd.nome}
            else:
                diario["curso"] = {"codigo": co_curso, "nome": diario.get("curso_descricao") or f"Curso {co_curso}"}
        else:
            diario["curso"] = {"codigo": "", "nome": diario.get("curso_descricao") or "Curso Desconhecido"}

        if turma_nova:
            diario["turma"] = turma_nova
        elif diario_re and len(diario_re[0]) > CODIGO_DIARIO_TURMA_INDEX:
            diario["turma"] = ".".join(diario_re[0][0 : CODIGO_DIARIO_TURMA_INDEX + 1])
        elif pratica_re and len(pratica_re[0]) > CODIGO_DIARIO_TURMA_INDEX:
            diario["turma"] = ".".join(pratica_re[0][0 : CODIGO_DIARIO_TURMA_INDEX + 1])

        if componente_novo:
            diario["componente"] = componente_novo
        elif diario_re and len(diario_re[0]) > CODIGO_DIARIO_DISCIPLINA_INDEX:
            diario["componente"] = diario_re[0][CODIGO_DIARIO_DISCIPLINA_INDEX]
        elif pratica_re and len(pratica_re[0]) > CODIGO_PRATICA_SUFIXO_INDEX:
            diario["componente"] = pratica_re[0][CODIGO_PRATICA_SUFIXO_INDEX]

        if id_diario_novo:
            diario["id_diario"] = str(id_diario_novo)
            diario["id_diario_clean"] = int(id_diario_novo) if str(id_diario_novo).isnumeric() else None
        elif diario_re and len(diario_re[0]) > CODIGO_DIARIO_ID_DIARIO_INDEX:
            id_diario_hash = diario_re[0][CODIGO_DIARIO_ID_DIARIO_INDEX]
            diario["id_diario"] = id_diario_hash
            diario["id_diario_clean"] = int(id_diario_hash[1:]) if id_diario_hash else None

        def _merge_extra_urls(diario: dict, ava: dict):
            id_diario = diario.get("id_diario_clean", None)

            if diario.get("can_set_visibility") and id_diario:
                diario["can_check_grades"] = True
                diario["checkgradesurl"] = reverse(
                    "painel:checkgrades", kwargs={"id_ambiente": ava["ambiente"]["id"], "id_diario": id_diario}
                )
                diario["mensagemurl"] = f"{settings.SUAP_AUTH['BASE_URL']}/edu/enviar_mensagem/?diario={id_diario}"

            if id_diario:
                diario["suapsurl"] = f"{settings.SUAP_AUTH['BASE_URL']}/edu/meu_diario/{id_diario}/1/"
                if diario.get("can_set_visibility"):
                    diario["gradesurl"] = re.sub("/course/view", "/grade/report/grader/index", diario["viewurl"])
                else:
                    diario["gradesurl"] = re.sub("/course/view", "/grade/report/overview/index", diario["viewurl"])

        if diario.get("id_diario_clean"):
            _merge_extra_urls(diario, ambiente)

        return {**diario, **ambiente}

    def _get_diarios(params: Dict[str, Any]):
        logger.debug(f"Consultando API do Moodle para o ambiente {params['ambiente'].nome} com os parâmetros: {params}")

        try:
            ambiente = params["ambiente"]
            ambientedict = {
                "ambiente": {
                    "id": ambiente.id,
                    "titulo": ambiente.nome,
                    "cor_mestra": ambiente.cor_mestra,
                }
            }

            querystrings = {
                k: v for k, v in params.items() if k not in ["ambiente", "results"] and str(v).strip() != ""
            }

            if "q" in querystrings:
                querystrings["q"] = urllib.parse.quote(querystrings["q"])

            result = get_json_api(ambiente, "get_diarios", **querystrings) or {}

            usuario_db_param = params.get("usuario_db")
            result["autoinscricoes"] = _filtrar_autoinscricoes(result.get("autoinscricoes", []), usuario_db_param)

            for k, v in result.items():
                if k not in params["results"]:
                    params["results"][k] = []

                if k == "autoinscricoes":

                    def _merge_vitrine(curso_vitrine: dict, amb_dict: dict):
                        ambiente_id = amb_dict["ambiente"]["id"]
                        curso_id = curso_vitrine["id"]

                        curso_vitrine["details_url"] = reverse(
                            "painel:curso_detalhes", kwargs={"id_ambiente": ambiente_id, "id_curso": curso_id}
                        )
                        return {**curso_vitrine, **amb_dict}

                    params["results"][k] += [_merge_vitrine(c, ambientedict) for c in v or []]

                elif k in CHAVES_ESTATICAS:
                    params["results"][k] += v or []

                else:
                    params["results"][k] += [_merge_course(diario, ambientedict) for diario in v or []]

        except Exception as e:
            logging.error(e)
            sentry_sdk.capture_exception(e)

    def deduplicate_and_sort(list_of_dict: Union[None, List[Dict[str, str]]], reverse: bool = False):
        deduplicated = [{"id": x, "label": y} for x, y in ({x["id"]: x["label"] for x in list_of_dict}).items()]
        sortedlist = sorted(deduplicated, key=lambda e: e["label"], reverse=reverse)
        return sortedlist

    has_ambiente = ambiente != "" and ambiente is not None and f"{ambiente}".isnumeric()
    ambientes = [ava for ava in Ambiente.cached() if (has_ambiente and int(ambiente) == ava.id) or not has_ambiente]
    logger.debug(f"Ambientes selecionados para consulta: {[a.moodle_base_api_url for a in ambientes]}")

    results = {
        "semestres": [],
        "ambientes": Ambiente.as_dict(),
        "disciplinas": [],
        "cursos": [],
        "diarios": [],
        "coordenacoes": [],
        "praticas": [],
        "reutilizaveis": [],
        "autoinscricoes": [],
    }

    requests = [
        {
            "ambiente": ava,
            "username": username.lower(),
            "usuario_db": usuario_db,
            "semestre": semestre,
            "situacao": situacao,
            "disciplina": disciplina,
            "curso": curso,
            "q": q,
            "page": page,
            "page_size": page_size,
            "results": results,
        }
        for ava in ambientes
    ]

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        executor.map(_get_diarios, requests)

    results["semestres"] = [{"id": "", "label": "Semestres... "}] + deduplicate_and_sort(
        results["semestres"], reverse=True
    )
    results["disciplinas"] = [{"id": "", "label": "Disciplinas..."}] + deduplicate_and_sort(results["disciplinas"])
    results["ambientes"] = [
        {
            "label": "Ambientes...",
            "id": "",
            "color": None,
        }
    ] + sorted(results["ambientes"], key=lambda e: e["label"])

    codigos = [x["id"] for x in results["cursos"]]
    cursos = {}
    for cod in codigos:
        curso_bd = get_curso_cached(cod)
        if curso_bd:
            cursos[cod] = curso_bd.nome

    cursos_a_criar = []
    for c in results["cursos"]:
        if c["id"] in cursos:
            c["label"] = f"{cursos[c['id']]}"
        else:
            c["label"] = f"Curso [{c['id']}], favor solicitar o cadastro"
            cursos_a_criar.append(Curso(codigo=c["id"], nome=f"Curso [{c['id']}], favor solicitar o cadastro"))

    if cursos_a_criar:
        try:
            Curso.objects.bulk_create(cursos_a_criar, ignore_conflicts=True)
            cache.delete("cursos")
        except Exception as e:
            logger.error(f"Erro ao tentar cadastrar cursos em lote: {e}")

    results["cursos"] = [{"id": "", "label": "Cursos..."}] + deduplicate_and_sort(results["cursos"])

    def course_sort_key(e):
        ano_periodo_str = str(e.get("turma_ano_periodo") or "")
        ano_periodo = 0

        match = re.search(r"(\d{4})\.?(\d)", ano_periodo_str)
        if match:
            ano_periodo = int(match.group(1) + match.group(2))
        else:
            match = re.search(r"(\d{4})", ano_periodo_str)
            if match:
                ano_periodo = int(match.group(1) + "0")

        return (-ano_periodo, (e.get("fullname") or "").lower())

    for k in results.keys():
        if k not in CHAVES_ESTATICAS and isinstance(results[k], list):
            if len(results[k]) > 0 and isinstance(results[k][0], dict) and "fullname" in results[k][0]:
                results[k] = sorted(results[k], key=course_sort_key)

    results["reutilizaveis"] = [
        {
            "id": x.id,
            "shortname": x.nome_arquivo,
            "fullname": x.curso_nome,
            "url": x.url_sem_dados,
            "donos": [
                {
                    "username": d.dono_backup.username,
                    "fullname": d.dono_backup.nome,
                }
                for d in x.donoarquivobackup_set.all()
            ],
        }
        for x in ArquivoBackup.objects.filter(donoarquivobackup__dono_backup__username=username).prefetch_related(
            "donoarquivobackup_set__dono_backup"
        )
    ]

    return results


def set_favourite_course(username: str, ava: str, courseid: int, favourite: int) -> dict:
    ava = get_object_or_404(Ambiente, nome=ava)

    return (
        get_json_api(ava, "set_favourite_course", username=username.lower(), courseid=courseid, favourite=favourite)
        or {}
    )


def set_visible_course(username: str, ava: str, courseid: int, visible: int) -> dict:
    ava = get_object_or_404(Ambiente, nome=ava)

    return get_json_api(ava, "set_visible_course", username=username.lower(), courseid=courseid, visible=visible) or {}


def set_user_preference(username: str, ava: str, name: str, value: str) -> dict:
    ava = get_object_or_404(Ambiente, nome=ava)

    return get_json_api(ava, "set_user_preference", username=username.lower(), name=name, value=value) or {}


def get_progresso(username: str, ambiente: str = None, cursos: str = None) -> dict:
    import threading

    lock = threading.Lock()

    has_ambiente = ambiente != "" and ambiente is not None and f"{ambiente}".isnumeric()
    ambientes = [ava for ava in Ambiente.cached() if (has_ambiente and int(ambiente) == ava.id) or not has_ambiente]

    results = []

    def _get_progresso_moodle(params: dict):
        ava = params["ambiente"]
        querystrings = {"username": params["username"]}
        if params.get("cursos"):
            querystrings["cursos"] = params["cursos"]

        try:
            data = get_json_api(ava, "get_progresso", **querystrings) or []
            if data:
                for item in data:
                    item["ambiente_id"] = ava.id

                with lock:
                    params["results"].extend(data)
        except Exception as e:
            logger.error(f"Erro em get_progresso ({ava.nome}): {e}")

    requests_args = [
        {
            "ambiente": ava,
            "username": username.lower(),
            "cursos": cursos,
            "results": results,
        }
        for ava in ambientes
    ]

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        executor.map(_get_progresso_moodle, requests_args)

    return {"progresso": results}
