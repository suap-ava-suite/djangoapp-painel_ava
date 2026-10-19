import json
import logging

from django.db import migrations

logger = logging.getLogger(__name__)


def _parse_json(val):
    if isinstance(val, (dict, list)):
        return val
    if isinstance(val, str) and val.strip():
        try:
            return json.loads(val)
        except Exception as exc:
            logger.warning("Falha ao decodificar JSON de a4_usuario: %s", exc)
    return None


def migrate_a4_data_to_suap_profile(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('public.a4_usuario')")
        if cursor.fetchone()[0] is None:
            return

        # Dumps antigos de a4_usuario não têm a coluna "vinculos"
        cursor.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'a4_usuario' AND column_name = 'vinculos'
            """)
        coluna_vinculos = 'u."vinculos"' if cursor.fetchone() else "NULL"

        cursor.execute(f"""
            SELECT
                u."id"::integer,
                u."username",
                u."nome_usual",
                u."nome_social",
                u."nome_registro",
                u."nome",
                u."email",
                u."email_secundario",
                u."email_google_classroom",
                u."email_academico",
                u."foto",
                u."tipo_usuario",
                u."settings",
                u."first_login",
                u."last_json",
                {coluna_vinculos}
            FROM "a4_usuario" u
            INNER JOIN "auth_user" au ON au."id" = u."id"::integer
            """)  # noqa: S608 - coluna_vinculos é constante interna, não entrada externa
        rows = cursor.fetchall()

    Perfil = apps.get_model("django_suap_auth_profile", "Perfil")
    DadosBrutos = apps.get_model("django_suap_auth_profile", "DadosBrutos")
    Vinculo = apps.get_model("django_suap_auth_profile", "Vinculo")

    for (
        user_id,
        username,
        nome_usual,
        nome_social,
        nome_registro,
        nome,
        email,
        email_secundario,
        email_google_classroom,
        email_academico,
        foto,
        tipo_usuario,
        user_settings,
        first_login,
        last_json,
        vinculos,
    ) in rows:
        parsed_settings = _parse_json(user_settings)
        if not isinstance(parsed_settings, dict):
            parsed_settings = {}

        parsed_last_json = _parse_json(last_json)
        campus = ""
        cpf = ""
        sexo = ""
        tipo_vinculo = ""
        if isinstance(parsed_last_json, dict):
            campus = str(parsed_last_json.get("campus") or "")[:100]
            cpf = str(parsed_last_json.get("cpf") or "")[:20]
            sexo = str(parsed_last_json.get("sexo") or "")[:10]
            tipo_vinculo = str(parsed_last_json.get("tipo_vinculo") or "")[:100]

        Perfil.objects.update_or_create(
            user_id=user_id,
            defaults={
                "matricula": (username or "")[:50],
                "nome_usual": (nome_usual or "")[:256],
                "nome_social": (nome_social or "")[:256],
                "nome_registro": (nome_registro or nome or "")[:256],
                "campus": campus,
                "cpf": cpf,
                "sexo": sexo,
                "tipo_vinculo": tipo_vinculo,
                "email_secundario": (email_secundario or "")[:254],
                "email_google_classroom": (email_google_classroom or "")[:254],
                "email_academico": (email_academico or "")[:254],
                "email_preferencial": (email or "")[:254],
                "url_foto_150x200": (foto or "")[:500],
                "tipo_usuario": (tipo_usuario or "")[:100],
                "settings": parsed_settings,
                "first_login": first_login,
            },
        )

        if isinstance(parsed_last_json, dict):
            DadosBrutos.objects.update_or_create(
                user_id=user_id,
                defaults={"data": parsed_last_json},
            )

        parsed_vinculos = _parse_json(vinculos)
        meus_vinculos = []
        if isinstance(parsed_vinculos, dict):
            meus_vinculos = parsed_vinculos.get("results") or parsed_vinculos.get("meus_vinculos") or []
        elif isinstance(parsed_vinculos, list):
            meus_vinculos = parsed_vinculos

        if isinstance(meus_vinculos, list):
            for item in meus_vinculos:
                if isinstance(item, dict):
                    det = item.get("detalhamento") if isinstance(item.get("detalhamento"), dict) else {}
                    Vinculo.objects.update_or_create(
                        user_id=user_id,
                        identificador=str(item.get("identificador", ""))[:50],
                        defaults={
                            "tipo": str(item.get("tipo") or "")[:50],
                            "campus": str(item.get("campus") or det.get("campus") or "")[:256] or None,
                            "cargo": str(item.get("cargo") or det.get("cargo") or "")[:256] or None,
                            "categoria": str(item.get("categoria") or det.get("categoria") or "")[:256] or None,
                            "modalidade": str(item.get("modalidade") or det.get("modalidade") or "")[:256] or None,
                            "nivel_ensino": str(item.get("nivel_ensino") or det.get("nivel_ensino") or "")[:256]
                            or None,
                            "curso": str(item.get("curso") or det.get("curso") or "")[:256] or None,
                            "ativo": item.get("ativo") if item.get("ativo") is not None else det.get("ativo"),
                            "detalhamento": det,
                            "estrangeiro": bool(item.get("estrangeiro", False)),
                        },
                    )


class Migration(migrations.Migration):

    dependencies = [
        ("painel", "0030_create_auth_user_from_a4"),
        ("django_suap_auth_profile", "0008_dadosbrutos_user_vinculo_user"),
    ]

    operations = [
        migrations.RunPython(
            migrate_a4_data_to_suap_profile,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
