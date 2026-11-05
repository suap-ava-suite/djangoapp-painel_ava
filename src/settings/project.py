"""Versão e ambiente do Painel.

- ``APP_VERSION``: lida do ``pyproject.toml`` (fonte única da versão). Na imagem Docker ele fica em
  ``/app/pyproject.toml``; no repositório, na raiz do projeto.
- ``APP_ENVIRONMENT``: ``local``, ``test`` ou ``production``. Vem da variável ``APP_ENVIRONMENT``, definida no
  build da imagem (``--build-arg APP_ENVIRONMENT=...``); sem ela, ``local``.
- ``APP_RELEASE``: o nome da release, igual à tag do git (``1.2.3`` em produção, ``1.2.3-test`` em teste).
"""

import os
import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"
VERSAO_DESCONHECIDA = "0.0.0"
AMBIENTE_PADRAO = "local"
AMBIENTE_PRODUCAO = "production"


def ler_versao(caminho: Path = PYPROJECT) -> str:
    """Versão do ``[project]`` do ``pyproject.toml``; ``VERSAO_DESCONHECIDA`` se o arquivo faltar ou for inválido."""
    try:
        with caminho.open("rb") as arquivo:
            return str(tomllib.load(arquivo)["project"]["version"])
    except OSError, tomllib.TOMLDecodeError, KeyError, TypeError:
        return VERSAO_DESCONHECIDA


def nome_da_release(versao: str, ambiente: str) -> str:
    """Mesmo nome da tag do git: sem sufixo em produção, ``<versão>-<ambiente>`` nos demais."""
    return versao if ambiente == AMBIENTE_PRODUCAO else f"{versao}-{ambiente}"


APP_VERSION = ler_versao()
APP_ENVIRONMENT = os.environ.get("APP_ENVIRONMENT", "").strip() or AMBIENTE_PADRAO
APP_RELEASE = nome_da_release(APP_VERSION, APP_ENVIRONMENT)
