// Classificação de falhas de rede/HTTP no navegador, para informar o usuário e
// etiquetar o erro no Sentry. O navegador não expõe a causa real de um `fetch`
// rejeitado (DNS, TLS, proxy...), então usamos sinais indiretos.
// Script clássico (não módulo): expõe `window.ErrosRede` e, no Node, `module.exports`.
(function (raiz) {
    const MENSAGENS = {
        offline: 'Sem conexão com a internet. Verifique sua rede e tente novamente.',
        timeout: 'A conexão está lenta e a resposta demorou demais.',
        http_403: 'Sua sessão expirou ou é inválida. Recarregue a página e tente novamente.',
        http_5xx: 'O servidor está com instabilidade no momento. Tente novamente em instantes.',
        http: 'Não foi possível concluir a operação.',
        rede: 'Não foi possível conectar ao servidor. Verifique sua conexão.',
    };

    // Causas que não indicam defeito nosso e não devem ir ao Sentry.
    const DESCARTAVEIS = ['navegando', 'aba_oculta'];

    let paginaSaindo = false;
    if (raiz.addEventListener) {
        raiz.addEventListener('pagehide', () => {
            paginaSaindo = true;
        });
        raiz.addEventListener('pageshow', () => {
            paginaSaindo = false;
        });
    }

    const ehErroDeRede = (error) =>
        error instanceof TypeError ||
        error?.code === 'ERR_NETWORK' ||
        /load failed|failed to fetch|networkerror/i.test(error?.message || '');

    const statusDe = (error) => error?.status ?? error?.response?.status ?? null;

    // Lê o ambiente em tempo de chamada para poder ser simulado nos testes.
    const lerAmbiente = (env) => {
        const nav = env.navigator || {};
        const conexao = nav.connection || {};
        return {
            online: nav.onLine,
            visibilidade: env.document?.visibilityState,
            saindo: env.paginaSaindo ?? paginaSaindo,
            tipoConexao: conexao.effectiveType,
            rtt: conexao.rtt,
            downlink: conexao.downlink,
        };
    };

    // Retorna { causa, descartavel, mensagem, detalhes }.
    function classificarFalha(error, env = raiz) {
        const amb = lerAmbiente(env);
        const status = statusDe(error);
        const detalhes = {
            online: amb.online,
            visibilidade: amb.visibilidade,
            tipo_conexao: amb.tipoConexao,
            rtt: amb.rtt,
            downlink: amb.downlink,
            http_status: status,
        };

        let causa;
        if (status === 403) {
            causa = 'http_403';
        } else if (status >= 500) {
            causa = 'http_5xx';
        } else if (status >= 400) {
            causa = 'http';
        } else if (error?.name === 'AbortError' || error?.name === 'TimeoutError' || error?.code === 'ECONNABORTED') {
            causa = 'timeout';
        } else if (ehErroDeRede(error)) {
            if (amb.saindo) causa = 'navegando';
            else if (amb.online === false) causa = 'offline';
            else if (amb.visibilidade === 'hidden') causa = 'aba_oculta';
            else causa = 'desconhecida';
        } else {
            causa = 'outro';
        }

        return {
            causa,
            descartavel: DESCARTAVEIS.includes(causa),
            mensagem: mensagemParaUsuario(causa),
            detalhes,
        };
    }

    function mensagemParaUsuario(causa) {
        return MENSAGENS[causa] || MENSAGENS.rede;
    }

    // Acrescenta o código do evento (ID do Sentry) à mensagem, quando existir.
    function comCodigo(texto, eventId) {
        return eventId ? `${texto} (Código do erro: ${eventId})` : texto;
    }

    // `fetch` com timeout e novas tentativas só para falhas de transporte e 5xx.
    // Erros HTTP definitivos (4xx) não são repetidos. Lança erro com `.status` quando !ok.
    async function buscarComRetry(url, { tentativas = 2, timeoutMs = 15000, esperaMs = 800, fetchFn } = {}) {
        const executar = fetchFn || raiz.fetch.bind(raiz);
        let ultimo;
        for (let i = 0; i < tentativas; i++) {
            const controle = new AbortController();
            const timer = setTimeout(() => controle.abort(), timeoutMs);
            try {
                const res = await executar(url, { signal: controle.signal });
                if (res.ok) return res;
                const erro = new Error(`HTTP ${res.status}`);
                erro.status = res.status;
                if (res.status < 500) throw erro;
                ultimo = erro;
            } catch (erro) {
                if (erro.status && erro.status < 500) throw erro;
                ultimo = erro;
            } finally {
                clearTimeout(timer);
            }
            if (i < tentativas - 1) await new Promise((r) => setTimeout(r, esperaMs));
        }
        throw ultimo;
    }

    // Aviso discreto (não bloqueante) com botão opcional "Tentar novamente".
    function mostrarAviso(texto, { aoTentarNovamente, doc = raiz.document } = {}) {
        if (!doc) return null;
        raiz.track?.('aviso_modal_exibir');
        doc.getElementById('aviso-rede')?.remove();

        const caixa = doc.createElement('div');
        caixa.id = 'aviso-rede';
        caixa.setAttribute('role', 'status');
        caixa.setAttribute('aria-live', 'polite');
        caixa.style.cssText =
            'position:fixed;left:50%;bottom:1rem;transform:translateX(-50%);z-index:2000;' +
            'max-width:90vw;padding:.75rem 1rem;border-radius:.5rem;background:#333;color:#fff;' +
            'box-shadow:0 2px 8px rgba(0,0,0,.3);display:flex;gap:.75rem;align-items:center;font-size:.9rem;';

        const span = doc.createElement('span');
        span.style.userSelect = 'all';
        span.textContent = texto;
        caixa.appendChild(span);

        if (aoTentarNovamente) {
            const botao = doc.createElement('button');
            botao.type = 'button';
            botao.className = 'btn btn-sm btn-light';
            botao.textContent = 'Tentar novamente';
            botao.addEventListener('click', () => {
                caixa.remove();
                aoTentarNovamente();
            });
            caixa.appendChild(botao);
        }

        const fechar = doc.createElement('button');
        fechar.type = 'button';
        fechar.className = 'btn-close btn-close-white';
        fechar.setAttribute('aria-label', 'Fechar aviso');
        fechar.addEventListener('click', () => caixa.remove());
        caixa.appendChild(fechar);

        doc.body.appendChild(caixa);
        return caixa;
    }

    // Diálogo modal (substitui o `alert` nativo, que bloqueia a página e não tem design).
    // Usa o markup de `modals/aviso-modal.html`; sem ele, recorre ao `alert`.
    // Fecha com o botão, Esc ou clique fora. Devolve uma Promise resolvida ao fechar.
    function mostrarDialogo({ titulo = 'Não foi possível concluir', mensagem = '', codigo, causa, doc = raiz.document, navegador = raiz.navigator } = {}) {
        raiz.track?.('erro_rede_dialogo_exibir', { causa: causa || 'desconhecida' });
        const modal = doc?.getElementById('aviso-modal');
        if (!modal) {
            raiz.alert?.(comCodigo(mensagem, codigo));
            return Promise.resolve();
        }
        const el = (id) => doc.getElementById(id);
        el('aviso-modal-title').textContent = titulo;
        el('aviso-modal-message').textContent = mensagem;

        const blocoCodigo = el('aviso-modal-codigo');
        const copiar = el('aviso-modal-copiar');
        if (codigo) {
            el('aviso-modal-codigo-valor').textContent = codigo;
            blocoCodigo.classList.remove('hidden');
        } else {
            blocoCodigo.classList.add('hidden');
        }
        copiar.textContent = 'Copiar';
        copiar.onclick = async () => {
            try {
                await navegador.clipboard.writeText(codigo);
                copiar.textContent = 'Copiado';
            } catch (e) {
                copiar.textContent = 'Selecione e copie';
            }
        };

        const fechar = el('aviso-modal-fechar');
        const anterior = doc.activeElement;
        return new Promise((resolver) => {
            const aoTeclar = (ev) => {
                if (ev.key === 'Escape') encerrar();
            };
            const encerrar = () => {
                modal.classList.add('hidden');
                doc.removeEventListener('keydown', aoTeclar);
                anterior?.focus?.();
                resolver();
            };
            fechar.onclick = encerrar;
            modal.onclick = (ev) => {
                if (ev.target === modal) encerrar();
            };
            doc.addEventListener('keydown', aoTeclar);
            modal.classList.remove('hidden');
            fechar.focus?.();
        });
    }

    const api = { classificarFalha, mensagemParaUsuario, comCodigo, buscarComRetry, mostrarAviso, mostrarDialogo, DESCARTAVEIS };
    raiz.ErrosRede = api;
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
