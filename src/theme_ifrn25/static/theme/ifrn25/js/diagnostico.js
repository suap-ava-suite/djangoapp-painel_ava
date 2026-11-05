// Diagnóstico de usuário (somente superusuários): abas "Personificar" e "Auto inscrição".
// Todo texto vindo do servidor entra com textContent (nunca innerHTML).
// Eventos do GA4 via window.track, só com categorias e contagens: nunca username, nome, curso ou regra.
// Script clássico: no Node expõe as funções puras via module.exports (para testes).
(function (raiz) {
    const MOTIVOS_BLOQUEIO = {
        inexistente: 'O usuário não existe no Painel (nunca fez login).',
        proprio_usuario: 'Você não pode personificar a si mesmo.',
        alvo_superuser: 'Não é permitido personificar outro superusuário.',
        inativo: 'O usuário está inativo no Painel.',
    };
    const MOTIVOS_AUTOINSCRICAO = {
        ok: 'Atende à regra',
        regra_vazia: 'Regra vazia',
        usuario_inexistente_painel: 'Usuário não existe no Painel',
        regra_invalida: 'Regra inválida',
        erro_avaliacao: 'Erro ao avaliar a regra',
        regra_falsa: 'Não atende à regra',
    };
    const STATUS_AMBIENTE = {
        ok: 'Tem conta',
        sem_conta: 'Sem conta',
        endpoint_indisponivel: 'Endpoint indisponível (atualize o tool_painelava)',
        erro: 'Erro ao consultar',
    };

    function urlPara(modelo, username) {
        return modelo.replace('__username__', encodeURIComponent(username));
    }

    function paramsConsulta(dados) {
        const ambientes = (dados && dados.ambientes) || [];
        return {
            resultado: dados && dados.existe_no_painel ? 'encontrado' : 'nao_encontrado',
            ambientes_com_conta: ambientes.filter((a) => a.status === 'ok').length,
            ambientes_indisponiveis: ambientes.filter((a) => a.status === 'endpoint_indisponivel' || a.status === 'erro').length,
        };
    }

    function paramsAutoinscricao(dados) {
        const cursos = ((dados && dados.ambientes) || []).flatMap((a) => a.cursos || []);
        const contagem = {};
        cursos.filter((c) => !c.atende).forEach((c) => {
            contagem[c.motivo] = (contagem[c.motivo] || 0) + 1;
        });
        const principal = Object.keys(contagem).sort((a, b) => contagem[b] - contagem[a])[0] || 'nenhum';
        return {
            cursos_total: cursos.length,
            cursos_atende: cursos.filter((c) => c.atende).length,
            cursos_nao_atende: cursos.filter((c) => !c.atende).length,
            motivo_principal: principal,
        };
    }

    function formatarData(valor) {
        if (!valor) {
            return 'nunca';
        }
        const data = typeof valor === 'number' ? new Date(valor * 1000) : new Date(valor);
        return isNaN(data) ? '—' : data.toLocaleString('pt-BR');
    }

    function iniciar(d) {
        const overlay = d.getElementById('diagnostico-modal');
        if (!overlay) {
            return;
        }
        const track = (evento, params) => raiz.track?.(evento, params);
        const form = d.getElementById('diagnostico-form');
        const campo = d.getElementById('diagnostico-username');
        const status = d.getElementById('diagnostico-status');
        const resultado = d.getElementById('diagnostico-resultado');
        const painelPersonificar = d.getElementById('diagnostico-painel-personificar');
        const painelAutoinscricao = d.getElementById('diagnostico-painel-autoinscricao');
        const regraModal = d.getElementById('diagnostico-regra-modal');
        const regraTitulo = d.getElementById('diagnostico-regra-titulo');
        const regraCorpo = d.getElementById('diagnostico-regra-corpo');
        const regraFechar = d.getElementById('diagnostico-regra-fechar');
        let botaoQueAbriuRegra = null;
        const abas = Array.from(overlay.querySelectorAll('[role="tab"]'));
        let usernameAtual = '';
        let autoinscricaoCarregada = false;
        let controlador = null;

        const el = (tag, texto, classe) => {
            const no = d.createElement(tag);
            if (texto !== undefined && texto !== null) {
                no.textContent = String(texto);
            }
            if (classe) {
                no.className = classe;
            }
            return no;
        };
        const falha = (texto, detalhe) => {
            const bloco = el('div', null, 'diagnostico-alerta');
            bloco.appendChild(el('p', texto));
            if (detalhe) {
                const mais = el('details');
                mais.appendChild(el('summary', 'Detalhe técnico'));
                mais.appendChild(el('code', detalhe));
                bloco.appendChild(mais);
            }
            return bloco;
        };
        const tabela = (cabecalhos, linhas) => {
            const t = el('table', null, 'diagnostico-tabela');
            const thead = t.createTHead().insertRow();
            cabecalhos.forEach((c) => thead.appendChild(el('th', c)));
            const tbody = t.createTBody();
            linhas.forEach((linha) => {
                const tr = tbody.insertRow();
                linha.forEach((celula) => {
                    const td = tr.insertCell();
                    if (celula instanceof raiz.Node) {
                        td.appendChild(celula);
                    } else {
                        td.textContent = celula === undefined || celula === null ? '—' : String(celula);
                    }
                });
            });
            return t;
        };

        const buscar = async (url, etapa) => {
            controlador = new AbortController();
            const resposta = await fetch(url, {
                credentials: 'same-origin',
                headers: { Accept: 'application/json' },
                signal: controlador.signal,
            });
            if (!resposta.ok) {
                let mensagem = `HTTP ${resposta.status}`;
                try {
                    mensagem = (await resposta.json()).error || mensagem;
                } catch (e) {
                    // corpo não é JSON: mantém o código HTTP
                }
                track('diagnostico_erro', { etapa, status: resposta.status });
                const erro = new Error(mensagem);
                erro.http = resposta.status;
                throw erro;
            }
            return resposta.json();
        };

        const abrir = () => {
            overlay.classList.remove('hidden');
            d.addEventListener('keydown', aoPressionarTecla);
            track('diagnostico_abrir');
            campo.focus();
        };
        const regraAberta = () => !regraModal.classList.contains('hidden');
        const fecharRegra = () => {
            regraModal.classList.add('hidden');
            regraCorpo.replaceChildren();
            botaoQueAbriuRegra?.focus();
        };
        const fechar = (acao) => {
            controlador?.abort();
            if (regraAberta()) {
                fecharRegra();
            }
            overlay.classList.add('hidden');
            d.removeEventListener('keydown', aoPressionarTecla);
            track('diagnostico_fechar', { acao });
        };
        const aoPressionarTecla = (evento) => {
            if (evento.key !== 'Escape') {
                return;
            }
            // Esc fecha primeiro a regra aberta; só depois o diagnóstico
            if (regraAberta()) {
                fecharRegra();
            } else {
                fechar('esc');
            }
        };

        const selecionarAba = (aba, registrar) => {
            abas.forEach((botao) => {
                const ativa = botao.dataset.aba === aba;
                botao.setAttribute('aria-selected', String(ativa));
                botao.tabIndex = ativa ? 0 : -1;
                d.getElementById(botao.getAttribute('aria-controls')).classList.toggle('hidden', !ativa);
            });
            if (registrar) {
                track('diagnostico_aba', { aba });
            }
            if (aba === 'autoinscricao' && !autoinscricaoCarregada) {
                carregarAutoinscricao();
            }
        };

        const renderPersonificar = (dados) => {
            painelPersonificar.replaceChildren();
            painelPersonificar.appendChild(
                el('p', 'A personificação vale só no Painel AVA: ela não personifica no Moodle nem no SUAP.', 'diagnostico-aviso')
            );
            const u = dados.usuario;
            if (u) {
                const lista = el('dl', null, 'diagnostico-dados');
                [
                    ['Nome', u.nome],
                    ['Username', u.username],
                    ['E-mail', u.email || '—'],
                    ['Tipo', u.perfil?.tipo_usuario],
                    ['Campus', u.perfil?.campus],
                    ['Curso', u.perfil?.curso],
                    ['Situação', u.perfil?.situacao],
                    ['Superusuário', u.is_superuser ? 'sim' : 'não'],
                    ['Ativo', u.is_active ? 'sim' : 'não'],
                    ['Último login no Painel', formatarData(u.last_login)],
                ].forEach(([rotulo, valor]) => {
                    lista.appendChild(el('dt', rotulo));
                    lista.appendChild(el('dd', valor || '—'));
                });
                painelPersonificar.appendChild(lista);
                if (u.matriculas.length) {
                    painelPersonificar.appendChild(el('h3', 'Vínculos (ordem usada em outras_matriculas)'));
                    painelPersonificar.appendChild(
                        tabela(
                            ['#', 'Tipo', 'Campus', 'Curso', 'Nível', 'Modalidade', 'Ativo'],
                            u.matriculas.map((m) => [m.indice, m.tipo, m.campus, m.curso, m.nivel_ensino, m.modalidade, m.ativo ? 'sim' : 'não'])
                        )
                    );
                }
            } else {
                painelPersonificar.appendChild(el('p', MOTIVOS_BLOQUEIO.inexistente, 'diagnostico-alerta'));
            }

            painelPersonificar.appendChild(el('h3', 'Ambientes Moodle'));
            painelPersonificar.appendChild(
                tabela(
                    ['Ambiente', 'Situação', 'Conta suspensa', 'Último acesso', 'Inscrições ativas', 'Inscrições suspensas'],
                    dados.ambientes.map((a) => [
                        a.ambiente.nome,
                        a.mensagem ? `${STATUS_AMBIENTE[a.status] || a.status}: ${a.mensagem}` : STATUS_AMBIENTE[a.status] || a.status,
                        a.conta ? (a.conta.suspended ? 'sim' : 'não') : '—',
                        a.conta ? formatarData(a.conta.lastaccess) : '—',
                        a.inscricoes ? a.inscricoes.active : '—',
                        a.inscricoes ? a.inscricoes.suspended : '—',
                    ])
                )
            );

            const acoes = el('div', null, 'diagnostico-acoes');
            const botao = el('button', 'Personificar', 'diagnostico-btn');
            botao.type = 'button';
            if (dados.pode_personificar) {
                botao.addEventListener('click', () => {
                    track('diagnostico_personificar', { permitido: 'sim' });
                    const url = new URL(overlay.dataset.urlPersonificar, raiz.location.origin);
                    url.searchParams.set('username', usernameAtual);
                    url.searchParams.set('next', '/');
                    raiz.location.assign(url.toString());
                });
            } else {
                botao.disabled = true;
                painelPersonificar.appendChild(el('p', MOTIVOS_BLOQUEIO[dados.motivo_bloqueio] || 'Personificação indisponível.', 'diagnostico-alerta'));
                track('diagnostico_personificar_bloqueado', { motivo: dados.motivo_bloqueio || 'desconhecido' });
            }
            acoes.appendChild(botao);
            if (u) {
                // Mesmo JSON da ação "Exportar" do admin de usuários (download direto)
                const exportar = el('a', 'Exportar', 'diagnostico-btn');
                exportar.href = urlPara(overlay.dataset.urlExportar, u.username);
                exportar.setAttribute('download', '');
                exportar.addEventListener('click', () => track('diagnostico_exportar'));
                acoes.appendChild(exportar);
                // Edição do usuário no admin, em nova aba para não perder o diagnóstico
                const editar = el('a', 'Editar', 'diagnostico-btn');
                editar.href = u.url_editar;
                editar.target = '_blank';
                editar.rel = 'noopener';
                editar.addEventListener('click', () => track('diagnostico_editar'));
                acoes.appendChild(editar);
            }
            painelPersonificar.appendChild(acoes);
        };

        // Blocos encaixados da explicação (django-rule-engine: RuleBlocks, rule_blocks.js/css)
        const blocosDaRegra = (arvore) => {
            const caixa = el('div', null, 'diagnostico-blocos');
            if (raiz.RuleBlocks) {
                raiz.RuleBlocks.render(caixa, arvore);
            } else {
                caixa.appendChild(el('p', 'Desenho da regra indisponível (rule_blocks.js não carregou).', 'diagnostico-aviso'));
            }
            return caixa;
        };

        // Detalhe da regra do curso, aberto num modal de 90% da tela (a tabela fica só com o resumo)
        const abrirRegra = (curso, botao) => {
            const detalhes = regraCorpo;
            detalhes.replaceChildren();
            regraTitulo.textContent = curso.fullname || 'Regra de autoinscrição';
            detalhes.appendChild(
                el(
                    'p',
                    `${curso.atende ? '✔' : '✖'} ${MOTIVOS_AUTOINSCRICAO[curso.motivo] || curso.motivo}`,
                    curso.atende ? 'diagnostico-sim' : 'diagnostico-nao'
                )
            );
            detalhes.appendChild(el('code', curso.regra || '(sem regra)', 'diagnostico-regra'));
            if (curso.detalhe) {
                detalhes.appendChild(el('p', curso.detalhe, 'diagnostico-alerta'));
            }
            if (curso.arvore) {
                detalhes.appendChild(blocosDaRegra(curso.arvore));
            }
            if (curso.indices_que_atenderiam.length) {
                detalhes.appendChild(
                    el(
                        'p',
                        `A regra usa outras_matriculas[0], mas passaria com o vínculo de índice ${curso.indices_que_atenderiam.join(', ')}.`,
                        'diagnostico-dica'
                    )
                );
            }
            const campos = Object.entries(curso.campos_da_regra || {});
            if (campos.length) {
                detalhes.appendChild(el('p', `Valores do usuário: ${campos.map(([k, v]) => `${k} = ${JSON.stringify(v)}`).join('; ')}`, 'diagnostico-valores'));
            }
            botaoQueAbriuRegra = botao;
            regraModal.classList.remove('hidden');
            regraFechar.focus();
            track('diagnostico_regra_abrir', { motivo: curso.motivo });
        };

        const renderCurso = (curso) => {
            const botao = el('button', 'Ver regra', 'diagnostico-btn diagnostico-btn-regra');
            botao.type = 'button';
            botao.addEventListener('click', () => abrirRegra(curso, botao));
            return [
                curso.fullname,
                el('span', `${curso.atende ? '✔' : '✖'} ${MOTIVOS_AUTOINSCRICAO[curso.motivo] || curso.motivo}`, curso.atende ? 'diagnostico-sim' : 'diagnostico-nao'),
                curso.visivel ? 'sim' : 'não',
                curso.inscricao,
                curso.aparece_no_painel ? 'sim' : 'não',
                botao,
            ];
        };

        const renderAutoinscricao = (dados) => {
            painelAutoinscricao.replaceChildren();
            if (!dados.existe_no_painel) {
                painelAutoinscricao.appendChild(el('p', 'Usuário não existe no Painel: nenhuma regra é atendida até o primeiro login.', 'diagnostico-alerta'));
            }
            dados.ambientes.forEach((a) => {
                painelAutoinscricao.appendChild(el('h3', a.ambiente.nome));
                if (a.status === 'endpoint_indisponivel' && a.fonte) {
                    painelAutoinscricao.appendChild(el('p', 'Endpoint de diagnóstico indisponível: cursos ocultos e inscrições suspensas não aparecem.', 'diagnostico-aviso'));
                } else if (!a.fonte) {
                    painelAutoinscricao.appendChild(falha(`${STATUS_AMBIENTE[a.status] || a.status}. ${a.mensagem}`, a.detalhe));
                    return;
                }
                if (!a.cursos.length) {
                    painelAutoinscricao.appendChild(el('p', 'Nenhum curso com autoinscrição.'));
                    return;
                }
                painelAutoinscricao.appendChild(
                    tabela(['Curso', 'Atende?', 'Visível', 'Inscrição', 'Aparece no Painel', 'Regra'], a.cursos.map((c) => renderCurso(c)))
                );
            });
            const ctx = dados.contexto;
            const detalhes = el('details', null, 'diagnostico-contexto');
            detalhes.appendChild(el('summary', 'Contexto usado nas regras (sem dados pessoais)'));
            detalhes.appendChild(el('pre', JSON.stringify(ctx, null, 2)));
            painelAutoinscricao.appendChild(detalhes);
        };

        async function carregarAutoinscricao() {
            autoinscricaoCarregada = true;
            painelAutoinscricao.replaceChildren(el('p', 'Consultando os cursos com autoinscrição em todos os ambientes…'));
            try {
                const dados = await buscar(urlPara(overlay.dataset.urlAutoinscricao, usernameAtual), 'autoinscricao');
                renderAutoinscricao(dados);
                track('diagnostico_autoinscricao', paramsAutoinscricao(dados));
            } catch (e) {
                autoinscricaoCarregada = false;
                if (e.name !== 'AbortError') {
                    if (!e.http) {
                        track('diagnostico_erro', { etapa: 'autoinscricao', status: 0 });
                    }
                    painelAutoinscricao.replaceChildren(el('p', `Falha: ${e.message}`, 'diagnostico-alerta'));
                }
            }
        }

        const consultar = async (evento) => {
            evento.preventDefault();
            const username = campo.value.trim();
            if (!username) {
                return;
            }
            controlador?.abort();
            usernameAtual = username;
            autoinscricaoCarregada = false;
            resultado.classList.add('hidden');
            status.textContent = 'Consultando o Painel e os ambientes Moodle…';
            try {
                const dados = await buscar(urlPara(overlay.dataset.urlUsuario, username), 'usuario');
                track('diagnostico_consultar', paramsConsulta(dados));
                status.textContent = dados.existe_no_painel ? '' : 'Usuário não encontrado no Painel.';
                renderPersonificar(dados);
                painelAutoinscricao.replaceChildren();
                resultado.classList.remove('hidden');
                selecionarAba('personificar', false);
            } catch (e) {
                if (e.name === 'AbortError') {
                    return;
                }
                if (!e.http) {
                    track('diagnostico_erro', { etapa: 'usuario', status: 0 });
                }
                track('diagnostico_consultar', { resultado: 'erro' });
                status.textContent = `Falha: ${e.message}`;
            }
        };

        form.addEventListener('submit', consultar);
        d.getElementById('diagnostico-fechar').addEventListener('click', () => fechar('botao'));
        regraFechar.addEventListener('click', fecharRegra);
        regraModal.addEventListener('click', (evento) => {
            if (evento.target === regraModal) {
                fecharRegra();
            }
        });
        overlay.addEventListener('click', (evento) => {
            if (evento.target === overlay) {
                fechar('fora');
            }
        });
        abas.forEach((botao) => botao.addEventListener('click', () => selecionarAba(botao.dataset.aba, true)));
        // O item do menu é renderizado pelo Vue depois do carregamento: delegação no document
        d.addEventListener('click', (evento) => {
            if (evento.target.closest && evento.target.closest('[data-diagnostico-abrir]')) {
                evento.preventDefault();
                abrir();
            }
        });
    }

    if (typeof document !== 'undefined' && raiz.addEventListener) {
        iniciar(document);
    }
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { urlPara, paramsConsulta, paramsAutoinscricao, formatarData };
    }
})(typeof window !== 'undefined' ? window : globalThis);
