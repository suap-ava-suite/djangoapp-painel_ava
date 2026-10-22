from django.contrib import admin
from django.contrib.admin import register
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils.html import format_html
from django_suap_auth.profile.admin import CustomUserAdmin

from base.admin import BaseModelAdmin
from painel.models import Ambiente, ConfiguracaoAba, Curso, Popup, Theme

####
# Inlines
####


####
# Admins
####
@register(Ambiente)
class AmbienteAdmin(BaseModelAdmin):
    list_display = ["nome", "url", "active"]
    search_fields = ["nome", "url"]
    list_filter = ["active"] + BaseModelAdmin.list_filter


@register(Curso)
class CursoAdmin(BaseModelAdmin):
    list_display = ["codigo", "nome"]
    search_fields = ["codigo", "nome"]
    list_filter = BaseModelAdmin.list_filter


@register(Popup)
class PopupAdmin(BaseModelAdmin):
    list_display = ["titulo", "start_at", "end_at"]
    search_fields = ["titulo", "url", "mensagem"]
    list_filter = ["active"] + BaseModelAdmin.list_filter


@register(Theme)
class ThemeAdmin(BaseModelAdmin):
    list_display = ["nome", "active"]
    search_fields = ["nome"]
    list_filter = ["active"] + BaseModelAdmin.list_filter


@register(ConfiguracaoAba)
class ConfiguracaoAbaAdmin(BaseModelAdmin):
    list_display = ["chave", "nome_desktop", "nome_mobile", "ordem", "sempre_visivel"]
    list_editable = ["nome_desktop", "nome_mobile", "ordem", "sempre_visivel"]
    search_fields = ["chave", "nome_desktop", "nome_mobile"]
    list_filter = ["sempre_visivel"] + BaseModelAdmin.list_filter


class PersonificarUserAdmin(CustomUserAdmin):
    """Admin de usuários com o link "Personificar" (views de django_suap_auth.impersonation), só para superusuário."""

    @admin.display(description="Personificar")
    def personificar(self, obj):
        if obj.is_superuser:
            # Personificar outro superusuário não é permitido pela biblioteca
            return "-"
        url = reverse("suap_auth_impersonation:impersonate", kwargs={"username": obj.username})
        return format_html('<a href="{}?next=/">Personificar</a>', url)

    def get_list_display(self, request):
        list_display = tuple(super().get_list_display(request))
        return list_display + ("personificar",) if request.user.is_superuser else list_display

    def get_readonly_fields(self, request, obj=None):
        readonly = tuple(super().get_readonly_fields(request, obj))
        return readonly + ("personificar",) if obj and request.user.is_superuser else readonly

    def get_fieldsets(self, request, obj=None):
        fieldsets = list(super().get_fieldsets(request, obj))
        if obj and request.user.is_superuser:
            fieldsets.insert(0, (None, {"fields": ("personificar",)}))
        return fieldsets


User = get_user_model()
try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass
admin.site.register(User, PersonificarUserAdmin)
