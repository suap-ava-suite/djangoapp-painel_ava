==========================
Diagnosticar usuário
==========================

Ferramenta para superusuários investigarem por que um usuário não vê um curso de autoinscrição ou
como ele aparece em cada Moodle (issue #128, chamado SUAP ©562849).

Acesso
======

Na gaveta do usuário (tema ``ifrn25``), bloco **Admins**, item **Diagnosticar**. O item, o modal e as
rotas só existem para superusuários e ficam indisponíveis durante uma personificação (as rotas
respondem ``409``). Para quem não é superusuário, as rotas respondem ``403``.

Rotas (somente ``GET``, JSON):

- ``/diagnostico/<username>/usuario/``
- ``/diagnostico/<username>/autoinscricao/``

Aba Personificar
================

Mostra os dados do usuário no Painel (nome, e-mail mascarado, perfil, situação, último login) e os
vínculos na mesma ordem de ``outras_matriculas``. Para cada ambiente Moodle ativo, informa se a conta
existe, se está suspensa, o último acesso e a quantidade de cursos com inscrição ativa e suspensa.

O botão **Personificar** usa ``django_suap_auth`` e vale **só no Painel**: não personifica no Moodle
nem no SUAP. Fica desabilitado quando o alvo é superusuário, é você mesmo, está inativo ou não existe
no Painel (nunca fez login).

Aba Auto inscrição
==================

Lista todos os cursos com ``restricoes_de_autoinscricao`` de cada ambiente, inclusive ocultos, e
informa para cada um:

- **Atende?** e o motivo: ``ok``, ``regra_falsa``, ``regra_vazia``, ``regra_invalida``,
  ``erro_avaliacao`` ou ``usuario_inexistente_painel``, com a mensagem de erro quando houver;
- as condições de nível superior da regra (quando ela é uma sequência de ``and`` ou de ``or``), com o
  resultado de cada uma;
- se a regra usa ``outras_matriculas[0]``, em quais índices de vínculo ela passaria (causa comum
  para quem tem mais de um vínculo);
- os valores do usuário citados pela regra (sem CPF, e-mail, telefone etc.);
- a inscrição no Moodle (``nenhuma``, ``ativa``, ``suspensa``, ``expirada``), a visibilidade do curso
  e se ele aparece no Painel.

Dependência do Moodle
=====================

Os dados vêm do endpoint ``get_diagnostico_usuario`` do ``tool_painelava`` (versão 4.5.022 ou
superior). Em um Moodle sem ele, o ambiente aparece como *Endpoint indisponível* e a aba Auto
inscrição usa a vitrine de ``get_diarios`` (sem cursos ocultos nem inscrições suspensas). As consultas
desta ferramenta não geram eventos no Sentry.

Eventos de analytics
====================

Nenhum evento leva username, nome, curso ou regra; só categorias e contagens.

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Evento
     - Parâmetros
   * - ``perfil_link_clicar``
     - ``destino=diagnosticar``
   * - ``diagnostico_abrir``
     - —
   * - ``diagnostico_consultar``
     - ``resultado`` (``encontrado``, ``nao_encontrado``, ``erro``), ``ambientes_com_conta``,
       ``ambientes_indisponiveis``
   * - ``diagnostico_aba``
     - ``aba`` (``personificar``, ``autoinscricao``)
   * - ``diagnostico_autoinscricao``
     - ``cursos_total``, ``cursos_atende``, ``cursos_nao_atende``, ``motivo_principal``
   * - ``diagnostico_personificar``
     - ``permitido=sim``
   * - ``diagnostico_personificar_bloqueado``
     - ``motivo`` (``alvo_superuser``, ``proprio_usuario``, ``inativo``, ``inexistente``)
   * - ``diagnostico_erro``
     - ``etapa`` (``usuario``, ``autoinscricao``), ``status`` (HTTP; ``0`` para falha de rede)
   * - ``diagnostico_fechar``
     - ``acao`` (``esc``, ``fora``, ``botao``)
