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

Rotas (somente ``GET``):

- ``/diagnostico/<username>/usuario/`` (JSON)
- ``/diagnostico/<username>/autoinscricao/`` (JSON)
- ``/diagnostico/<username>/exportar/`` (download do JSON de exportação; ``404`` se o usuário não existe
  no Painel)

Aba Personificar
================

Mostra os dados do usuário no Painel (nome, e-mail mascarado, perfil, situação, último login) e os
vínculos na mesma ordem de ``outras_matriculas``. Para cada ambiente Moodle ativo, informa se a conta
existe, se está suspensa, o último acesso e a quantidade de cursos com inscrição ativa e suspensa.
Quando a conta existe, **Ver conta** abre o perfil do usuário naquele Moodle (``/user/profile.php``),
numa nova aba.

O botão **Personificar** usa ``django_suap_auth`` e vale **só no Painel**: não personifica no Moodle
nem no SUAP. Fica desabilitado quando o alvo é superusuário, é você mesmo, está inativo ou não existe
no Painel (nunca fez login).

Quando o usuário existe no Painel, ao lado de **Personificar** aparecem:

- **Exportar**: baixa o mesmo JSON da ação *Exportar (JSON) com perfil, vínculos e dados brutos* do
  admin de usuários (``django_suap_auth``), só com este usuário;
- **Editar**: abre a tela de edição do usuário no admin, numa nova aba (issue #130).

Aba Auto inscrição
==================

Lista todos os cursos com ``restricoes_de_autoinscricao`` de cada ambiente, inclusive ocultos, numa
tabela-resumo. O botão **Ver regra** de cada curso abre o detalhe num modal que ocupa 90% da tela
(Esc fecha só esse modal). O nome do curso é um link para a página dele no Moodle
(``/course/view.php``), numa nova aba. Para cada curso, informa:

- **Atende?** e o motivo: ``ok``, ``regra_falsa``, ``regra_vazia``, ``regra_invalida``,
  ``erro_avaliacao`` ou ``usuario_inexistente_painel``, com a mensagem de erro quando houver;
- quando não atende, a regra desenhada em blocos encaixados (estilo Scratch), em verde o que foi
  atendido e em vermelho o que não foi, com o valor do usuário ao lado do esperado. Em
  ``$any``/``$all`` sobre ``outras_matriculas``, cada vínculo vira um item (rotulado por campus e
  curso), e o que chega mais perto de atender vem aberto. A explicação vem de
  ``django_rule_engine.explain_tree`` e o desenho de ``rule_widget/rule_blocks.js`` (django-rule-engine
  1.2.0);
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
   * - ``diagnostico_exportar``
     - —
   * - ``diagnostico_editar``
     - —
   * - ``diagnostico_conta_abrir``
     - —
   * - ``diagnostico_curso_abrir``
     - —
   * - ``diagnostico_personificar_bloqueado``
     - ``motivo`` (``alvo_superuser``, ``proprio_usuario``, ``inativo``, ``inexistente``)
   * - ``diagnostico_erro``
     - ``etapa`` (``usuario``, ``autoinscricao``), ``status`` (HTTP; ``0`` para falha de rede)
   * - ``diagnostico_fechar``
     - ``acao`` (``esc``, ``fora``, ``botao``)
   * - ``diagnostico_regra_abrir``
     - ``motivo`` (os mesmos valores de ``motivo_principal``)
