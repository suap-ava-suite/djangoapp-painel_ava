import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client


@pytest.fixture
def usuarios(db):
    User = get_user_model()
    admin = User.objects.create_superuser(username="admin", password="x", email="a@exemplo.test")
    comum = User.objects.create_user(username="comum", password="x")
    outro_admin = User.objects.create_superuser(username="outroadmin", password="x", email="o@exemplo.test")
    return admin, comum, outro_admin


def _cliente(user):
    client = Client()
    client.force_login(user)
    return client


def test_lista_mostra_link_personificar_so_para_nao_superusuario(usuarios):
    admin, comum, outro_admin = usuarios
    html = _cliente(admin).get("/admin/auth/user/").content.decode()
    assert "Personificar" in html
    assert "/auth/suap/impersonate/comum/" in html
    assert "/auth/suap/impersonate/outroadmin/" not in html


def test_tela_de_edicao_mostra_link_personificar(usuarios):
    admin, comum, _ = usuarios
    html = _cliente(admin).get(f"/admin/auth/user/{comum.pk}/change/").content.decode()
    assert "/auth/suap/impersonate/comum/" in html


def test_staff_sem_superusuario_nao_ve_personificar(db):
    User = get_user_model()
    staff = User.objects.create_user(username="staff", password="x", is_staff=True)
    staff.user_permissions.add(Permission.objects.get(codename="view_user"))
    html = _cliente(staff).get("/admin/auth/user/").content.decode()
    assert "impersonate" not in html
