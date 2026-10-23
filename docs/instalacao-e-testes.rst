===========================================
Instalação e Teste Local da Documentação
===========================================

Este documento explica como instalar as dependências necessárias, compilar e testar localmente a geração da
documentação do **Painel AVA** (``integrador-ava``) utilizando o tema Sphinx **``django-docs-theme``**.

1. Requisitos Prévios
======================

- Python 3.12+ (ou 3.14)
- Ambiente virtual (``venv``) ativado

2. Instalação das Dependências
==============================

No diretório raiz do projeto ``painel_ava``, ative seu ambiente virtual e instale os pacotes de documentação
definidos no ``pyproject.toml``:

.. code-block:: bash

   # Ativar o ambiente virtual
   source .venv/bin/activate

   # Instalar as dependências de documentação
   pip install sphinx myst-parser django-docs-theme>=0.1.4

Ou via extras declarados no ``pyproject.toml``:

.. code-block:: bash

   pip install -e ".[docs]"

3. Compilação Local da Documentação
===================================

Para gerar os arquivos HTML estáticos da documentação:

Opção A: Usando o comando ``sphinx-build`` (Recomendado)
--------------------------------------------------------

O parâmetro ``-W`` garante que avisos de sintaxe ou links quebrados sejam tratados como erros, garantindo uma
compilação 100% limpa:

.. code-block:: bash

   sphinx-build -W -b html docs docs/_build/html

Opção B: Usando o ``Makefile``
------------------------------

Você também pode navegar até a pasta ``docs/`` e utilizar o Makefile:

.. code-block:: bash

   cd docs
   make html

Os arquivos HTML gerados estarão localizados em ``docs/_build/html/``.

4. Servidor HTTP Local e Testes no Navegador
============================================

Para visualizar e testar interativamente a documentação no seu navegador sem erros de rotas estáticas:

.. code-block:: bash

   # 1. Entrar na pasta do build HTML
   cd docs/_build/html

   # 2. Iniciar o servidor HTTP do Python na porta 8000
   python3 -m http.server 8000

Abra seu navegador no endereço: `http://localhost:8000 <http://localhost:8000>`_

5. Automação CI/CD no GitHub Actions
====================================

O repositório possui workflows automatizados em ``.github/workflows/``:

- **Documentação (``docs.yml``)**:

  1. **Pull Requests**: Valida se a documentação compila sem avisos ou erros (``sphinx-build -W``).
  2. **Push na branch main**: Compila a documentação e publica automaticamente a versão atualizada no **GitHub Pages**.

- **Build, Deploy e Sentry (``build-deploy.yml``)**:

  1. **Publicação de imagem Docker**: Constrói e publica a imagem multi-arquitetura no Docker Hub ao publicar uma
     release/tag.
  2. **Deploy automatizado**: Atualiza o ambiente de homologação (``test``, tags com sufixo ``-test`` via Helm) ou os
     servidores de produção (``production``, via Docker Compose).
  3. **Registro no Sentry**: Registra a release, associa os commits locais
     (``sentry-cli releases set-commits --local``), finaliza a versão e notifica o deploy no ambiente correspondente
     (``test`` ou ``production``) utilizando a secret ``SENTRY_AUTH_TOKEN`` e as variáveis ``SENTRY_URL``,
     ``SENTRY_ORG`` e ``SENTRY_PROJECT``.

Sentry no navegador (JavaScript)
--------------------------------

Os erros de JavaScript do tema ``ifrn25`` (inclusive os de "Erro de comunicação com o servidor")
são enviados ao Sentry **somente** se a variável ``SENTRY_JS_DSN`` estiver definida. Ela é
independente de ``SENTRY_DNS`` (Django), então pode apontar para outro projeto do Sentry.

- ``SENTRY_JS_DSN``: DSN do projeto JavaScript. Sem ela, o SDK não é carregado e nada é enviado.
- ``SENTRY_JS_ENVIRONMENT``: ambiente (padrão: ``SENTRY_ENVIRONMENT`` ou ``local``).
- ``SENTRY_JS_SAMPLE_RATE``: porcentagem de erros reportados (padrão: ``100``).
- ``SENTRY_RELEASE``: release (padrão: versão da aplicação).

Erros originados em arquivos da pasta ``vendors`` são descartados.

Google Analytics e Clarity (theme_ifrn25)
-----------------------------------------

O tema ``ifrn25`` carrega GA4 e Microsoft Clarity com chaves **próprias**, independentes de
``GTAG_CODE`` e ``CLARITY_CODE`` (usadas pelo ``ifrn23``). Sem a variável, o serviço não é carregado.

- ``IFRN25_GTAG_CODE``: ID do GA4 (``G-XXXXXXX``).
- ``IFRN25_CLARITY_CODE``: ID do projeto Clarity.

``window.track(evento, params)`` (``theme_ifrn25/static/theme/ifrn25/js/analytics.js``) envia o evento
aos dois serviços; é no-op quando nenhum está carregado. Erros de JavaScript não tratados
(``error`` e ``unhandledrejection``) geram o evento ``js_error`` e as tags ``js_error`` e
``js_error_msg`` (mensagem cortada em 100 caracteres) no Clarity; erros tratados em ``reportJsError``
geram ``js_error_tratado``. Nunca envie dados pessoais nos eventos. O plano completo de eventos
está na issue #115.

CSRF atrás de proxy
~~~~~~~~~~~~~~~~~~~

Em produção (HTTPS atrás de proxy) o Django só aceita o ``Origin`` do navegador se ele estiver em
``DJANGO_CSRF_TRUSTED_ORIGINS`` (lista separada por vírgula, ex.: ``https://ava.ifrn.edu.br``). Sem isso, todo
``POST`` falha com "Verificação CSRF falhou" (403). Também são lidas ``DJANGO_CSRF_COOKIE_DOMAIN`` e
``DJANGO_CSRF_COOKIE_SECURE`` (padrão ``False``).

Falhas de rede e CSRF
~~~~~~~~~~~~~~~~~~~~~

O helper ``erros-rede.js`` classifica falhas de ``fetch``/``axios`` pela causa provável e a envia como tag
``causa_falha`` (com ``online``, ``visibilidade``, ``tipo_conexao``, ``rtt`` e ``http_status`` nos extras). Valores:
``offline``, ``timeout``, ``http_403``, ``http_5xx``, ``http``, ``desconhecida``, ``outro``, ``navegando`` e
``aba_oculta``. Os dois últimos (usuário saindo da página, aba em segundo plano) não são enviados ao Sentry.

Quando o erro é enviado, a mensagem ao usuário inclui o **código do erro** (ID do evento no Sentry, 32 caracteres);
se ele abrir um chamado, basta buscar esse ID no Sentry (``id:<código>``) para localizar o caso individual.

O usuário vê um aviso com a orientação adequada (por exemplo, recarregar a página em caso de 403 de CSRF) e, no
progresso dos diários, o botão "Tentar novamente". O carregamento do progresso tem timeout de 15 s e uma nova tentativa.

Testes do JavaScript (Node.js ≥ 20, sem dependências extras)::

    node --test src/painel/tests_js/erros-rede.test.js

O pytest também executa essa suíte (``painel/test_erros_rede_js.py``); ela é ignorada quando o Node.js não está
instalado.
