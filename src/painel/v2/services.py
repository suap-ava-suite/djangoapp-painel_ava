import logging
from enum import Enum

from django.contrib.auth import get_user_model

from painel.models import Ambiente
from painel.v2.brokers import SuapBroker

logger = logging.getLogger(__name__)


class RoomType(Enum):
    INICIO = (
        "inicio",
        "Início",
        "Início",
        "Continue de onde você parou",
        "fa-regular fa-house",
        0,
        False,
        True,
        None,
    )
    DIARIO = (
        "diario",
        "Diários",
        "Meus diários",
        "Diários de classe",
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-book-open h-4 w-4" aria-hidden="true"><path d="M12 7v14"></path><path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"></path></svg>',  # noqa: E501
        1,
        True,
        True,
        None,
    )
    COORDENACAO = (
        "coordenacao",
        "Coordenações",
        "Salas de coordenações",
        "Salas de coordenações dos cursos",
        "fa-solid fa-arrows-to-circle",
        2,
        False,
        True,
        None,
    )
    LABORATORIO = (
        "laboratorio",
        "Laboratórios",
        "Laboratórios de EaD",
        "Laboratórios para práticas de EaD disponibilizados no Ambiente Virtual de Aprendizagem",
        "fa-solid fa-flask",
        3,
        False,
        True,
        None,
    )
    AUTOINSCRICOES = (
        "autoinscricoes",
        "Auto-inscrições",
        "Auto-inscrições",
        "Cursos para auto-inscrição",
        "fa-brands fa-stripe-s",
        4,
        False,
        True,
        "Cursos abertos em que você pode se inscrever sem aprovação prévia.",
    )
    BACKUP = (
        "backup",
        "Backups",
        "Meus backups",
        "Backups",
        "fa-solid fa-box-archive",
        5,
        False,
        True,
        "Backups dos seus diários ou compartilhados com você.",
    )

    def __new__(
        cls,
        slug: str,
        rotulo_curto: str,
        rotulo_longo: str,
        dica: str,
        icon: str,
        ordem: int,
        selecionado: bool,
        ativo: bool,
        subtitulo: str = None,
    ):
        obj = object.__new__(cls)
        obj._value_ = slug
        obj.slug = slug
        obj.rotulo_curto = rotulo_curto
        obj.rotulo_longo = rotulo_longo
        obj.dica = dica
        obj.icon = icon
        obj.ordem = ordem
        obj.selecionado = selecionado
        obj.ativo = ativo
        obj.subtitulo = subtitulo
        return obj

    def to_dict(self) -> dict:
        data = {
            "slug": self.slug,
            "rotulo_curto": self.rotulo_curto,
            "rotulo_longo": self.rotulo_longo,
            "dica": self.dica,
            "icon": self.icon,
            "ordem": self.ordem,
            "selecionado": self.selecionado,
            "ativo": self.ativo,
        }
        if self.subtitulo:
            data["subtitulo"] = self.subtitulo
        return data

    @classmethod
    def as_list(cls) -> list:
        return [item.to_dict() for item in cls]

    @classmethod
    def get_by_slug(cls, slug: str):
        for item in cls:
            if item.slug == slug:
                return item
        return cls.INICIO


class TokenService:
    @classmethod
    def pair(cls, username: str, password: str) -> dict:
        suap_broker = SuapBroker()
        suap_broker.login(None, username, password)
        return suap_broker.generate_pair(username)

    @classmethod
    def refresh(cls, refresh_token: str) -> dict:
        suap_broker = SuapBroker()
        username = suap_broker.verify(refresh_token)
        if not username:
            raise ValueError("Token is invalid or expired")
        pair = suap_broker.generate_pair(username)
        return {"refresh": pair["refresh"], "access": pair["access"]}

    @classmethod
    def verify(cls, token: str) -> dict:
        suap_broker = SuapBroker()
        username = suap_broker.verify(token)
        if not username:
            raise ValueError("Token is invalid or expired")
        pair = suap_broker.generate_pair(username)
        return {"refresh": pair["refresh"], "access": pair["access"]}

    @classmethod
    def revoke(cls, token: str) -> dict:
        suap_broker = SuapBroker()
        username = suap_broker.verify(token)
        if not username:
            raise ValueError("Token is invalid or expired")

        revoke_list = []
        ambientes = Ambiente.cached() if hasattr(Ambiente, "cached") else Ambiente.objects.all()
        for ava in ambientes:
            revoke_list.append(
                {
                    "service_name": ava.nome,
                    "url": ava.url,
                    "revoked": True,
                    "duration": "PT0.1S",
                }
            )

        return {"detail": "Token revoked", "revoke_list": revoke_list}


class UsuarioService:
    @classmethod
    def info(cls, username: str) -> dict:
        User = get_user_model()
        user = User.objects.filter(username=username).first()
        if not user:
            return {
                "id": 0,
                "matricula": username,
                "identificacao": username,
                "nome_social": username,
                "nome_registro": username,
                "ultimo_nome": "",
                "nome_usual": username,
                "email": f"{username}@sememail.ifrn.edu.br",
                "email_preferencial": f"{username}@sememail.ifrn.edu.br",
                "foto": "",
                "url_foto_75x100": "",
                "url_foto_150x200": "",
                "tipo_vinculo": "Servidor",
                "tipo_usuario": "Servidor",
                "vinculo": {},
                "vinculos": [],
            }

        profile = getattr(user, "suap_profile", None)

        nome_usual = getattr(profile, "nome_usual", None) or user.first_name
        nome_registro = getattr(profile, "nome_registro", None) or f"{user.first_name} {user.last_name}".strip()
        tipo = getattr(profile, "tipo_usuario", "Servidor")
        raw_data = getattr(getattr(user, "suap_raw_data", None), "data", None) or {}
        foto_75 = getattr(profile, "url_foto_75x100", None) or raw_data.get("foto") or ""
        foto = getattr(profile, "url_foto_150x200", None) or foto_75

        return {
            "id": user.id,
            "matricula": user.username,
            "identificacao": user.username,
            "nome_social": getattr(profile, "nome_social", None) or nome_usual,
            "nome_registro": nome_registro,
            "ultimo_nome": user.last_name,
            "nome_usual": nome_usual,
            "cpf": "",
            "rg": "",
            "passaporte": "",
            "filiacao": ["", ""],
            "sexo": "",
            "data_nascimento": "",
            "data_de_nascimento": "",
            "naturalidade": "",
            "email": user.email,
            "email_secundario": getattr(profile, "email_secundario", ""),
            "email_google_classroom": getattr(profile, "email_google_classroom", ""),
            "email_academico": getattr(profile, "email_academico", ""),
            "email_preferencial": getattr(profile, "email_preferencial", None) or user.email,
            "foto": foto,
            "url_foto_75x100": foto_75 or foto,
            "url_foto_150x200": foto,
            "tipo_vinculo": tipo,
            "tipo_usuario": tipo,
            "vinculo": {
                "turno": "",
                "campus_curso": "",
                "campus": getattr(profile, "campus_sigla", ""),
                "curso": "",
                "matriz": "",
                "cargo": "",
                "ingresso": "",
                "ira": "",
                "categoria": "",
                "situacao": "",
                "situacao_sistemica": "",
                "matricula_regular": True,
            },
            "vinculos": [],
        }

    @classmethod
    def preferencia_get(cls, username: str) -> dict:
        User = get_user_model()
        user = User.objects.filter(username=username).first()
        if not user:
            return {"zoom": "100%", "configuracao": "Padrão"}
        profile = getattr(user, "suap_profile", None)
        settings_dict = getattr(profile, "settings", {}) if profile else {}
        zoom = settings_dict.get("accessibility", {}).get("zoom_level", 100) if isinstance(settings_dict, dict) else 100
        return {"zoom": f"{zoom}%", "configuracao": "Padrão"}

    @classmethod
    def preferencia_patch(cls, username: str, data: dict) -> dict:
        User = get_user_model()
        user = User.objects.filter(username=username).first()
        if user:
            profile = getattr(user, "suap_profile", None)
            if profile is None:
                try:
                    from django_suap_auth.profile.models import Perfil

                    profile, _ = Perfil.objects.get_or_create(user=user)
                except Exception:
                    profile = None
            if profile is not None:
                if not isinstance(profile.settings, dict):
                    profile.settings = {}
                acc = profile.settings.setdefault("accessibility", {})
                if "zoom" in data:
                    val_str = str(data["zoom"]).replace("%", "")
                    if val_str.isnumeric():
                        acc["zoom_level"] = int(val_str)
                profile.save()
        return data


class SalaService:
    @classmethod
    def tipo_list(cls, ava: str = "*") -> list:
        return RoomType.as_list()

    @classmethod
    def tipo_detail(cls, tipo: str) -> dict:
        room_type = RoomType.get_by_slug(tipo)
        detail = room_type.to_dict()
        detail["quantidade_salas"] = 0 if tipo == "inicio" else 5
        detail["suprimir"] = "Sala da Coordenação do Curso de " if tipo == "coordenacao" else None
        detail["filtros"] = (
            []
            if tipo in ["inicio", "autoinscricoes"]
            else [
                {
                    "slug": "situacao",
                    "tipo": "select",
                    "autocomplete": False,
                    "icone": "fa-solid fa-book",
                    "rotulo": "Situação",
                    "selecionado": "inprogress",
                    "opcoes": [
                        {"label": "Em andamento", "value": "inprogress"},
                        {"label": "Favoritos", "value": "favourites"},
                    ],
                }
            ]
        )
        detail["ordenacao"] = (
            None
            if tipo in ["inicio", "coordenacao", "autoinscricoes"]
            else {
                "selecionada": "data_acesso",
                "opcoes": [
                    {"value": "data_acesso", "direcao": "DESC", "rotulo": "Acesso mais recente"},
                    {"value": "titulo", "direcao": "ASC", "rotulo": "Título"},
                ],
            }
        )
        return detail

    @classmethod
    def quantidades(cls) -> dict:
        return {
            "inicio": 0,
            "diario": 0,
            "coordenacao": 0,
            "laboratorio": 0,
            "autoinscricoes": 0,
            "backup": 0,
        }

    @classmethod
    def salas_by_tipo(cls, tipo: str, ava: str = "*") -> list:
        return []

    @classmethod
    def progresso(cls, ava: str, ids: str) -> list:
        id_list = [i for i in ids.replace("/", ",").split(",") if i]
        return [{"id": i, "progress": 50, "hasprogress": True} for i in id_list]

    @classmethod
    def favorito_patch(cls, ava: str, id_sala: str, favorite: bool) -> dict:
        return {"favorite": favorite}

    @classmethod
    def visivel_patch(cls, ava: str, id_sala: str, visible: bool) -> dict:
        return {"visible": visible}


class NotificacaoService:
    @classmethod
    def sumario(cls) -> list:
        return [{"ava": "academico", "unreadcount": 0}]

    @classmethod
    def by_ava(cls, ava: str) -> dict:
        return {"result": [], "unreadcount": 0}

    @classmethod
    def by_ids(cls, ava: str, ids: str) -> dict:
        return {
            "id": 1,
            "useridfrom": -10,
            "useridto": 1,
            "subject": "Notificação de Teste",
            "shortenedsubject": "Teste",
            "text": "Conteúdo da notificação",
            "fullmessage": "Conteúdo da notificação",
            "fullmessageformat": 4,
            "fullmessagehtml": "<p>Conteúdo da notificação</p>",
            "smallmessage": "Notificação",
            "contexturl": "",
            "contexturlname": "",
            "timecreated": "2026-08-13T10:00:00Z",
            "timecreatedpretty": "há 1 hora",
            "timeread": None,
            "read": False,
            "deleted": False,
            "iconurl": "",
            "component": "system",
            "eventtype": "notification",
            "customdata": None,
        }

    @classmethod
    def patch(cls, ava: str, ids: str, is_read: bool) -> list:
        return [{"error": False, "data": {"notificationid": 1, "warnings": []}}]


class ConversaService:
    @classmethod
    def sumario(cls) -> list:
        return [{"ava": "academico", "unreadcount": 0, "favourites": 0}]

    @classmethod
    def by_ava(cls, ava: str) -> list:
        return []

    @classmethod
    def by_ids(cls, ava: str, ids: str) -> list:
        return []

    @classmethod
    def patch(cls, ava: str, id_conversa: str, is_read: bool) -> list:
        return [{"error": False, "data": None}]
