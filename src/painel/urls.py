from django.urls import path

from .apps import PainelConfig
from .diagnostico import diagnostico_autoinscricao, diagnostico_usuario
from .views import (
    change_menu_position,
    change_theme,
    checkgrades,
    completed_tour,
    curso_detalhes,
    dashboard,
    enrol_course,
    get_tour_status,
    unenrol_course,
)

app_name = PainelConfig.name


urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("curso/<int:id_ambiente>/<int:id_curso>/", curso_detalhes, name="curso_detalhes"),
    path("curso/<int:id_ambiente>/<int:id_curso>/enrol/", enrol_course, name="enrol_course_api"),
    path("curso/<int:id_ambiente>/<int:id_curso>/unenrol/", unenrol_course, name="unenrol_course"),
    path("change_theme/<theme>/", change_theme, name="change_theme"),
    path("settings/menu-position/", change_menu_position, name="menu_position"),
    path("diario/<id_ambiente>/<id_diario>/checkgrades/", checkgrades, name="checkgrades"),
    path("set_tour_completed/", completed_tour, name="set_tour_completed"),
    path("get_tour_status/", get_tour_status, name="get_tour_status"),
    path("diagnostico/<str:username>/usuario/", diagnostico_usuario, name="diagnostico_usuario"),
    path("diagnostico/<str:username>/autoinscricao/", diagnostico_autoinscricao, name="diagnostico_autoinscricao"),
]
