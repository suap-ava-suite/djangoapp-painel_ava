// Testes do helper de classificação de falhas de rede. Executar com: node --test src/painel/tests_js/erros-rede.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const vm = require('node:vm');

const JS_DIR = path.join(__dirname, '..', '..', 'theme_ifrn25', 'static', 'theme', 'ifrn25', 'js');
const { classificarFalha, mensagemParaUsuario, comCodigo, buscarComRetry, mostrarAviso } = require(path.join(JS_DIR, 'erros-rede.js'));

const ambiente = (extra = {}) => ({
    navigator: { onLine: true },
    document: { visibilityState: 'visible' },
    paginaSaindo: false,
    ...extra,
});

test('Load failed com ambiente normal é desconhecida e reportável', () => {
    const r = classificarFalha(new TypeError('Load failed'), ambiente());
    assert.equal(r.causa, 'desconhecida');
    assert.equal(r.descartavel, false);
});

test('Failed to fetch (Chrome) também é falha de rede', () => {
    assert.equal(classificarFalha(new TypeError('Failed to fetch'), ambiente()).causa, 'desconhecida');
});

test('sem conexão é offline', () => {
    const r = classificarFalha(new TypeError('Load failed'), ambiente({ navigator: { onLine: false } }));
    assert.equal(r.causa, 'offline');
    assert.match(r.mensagem, /Sem conexão/);
});

test('aba oculta é descartável', () => {
    const r = classificarFalha(new TypeError('Load failed'), ambiente({ document: { visibilityState: 'hidden' } }));
    assert.equal(r.causa, 'aba_oculta');
    assert.equal(r.descartavel, true);
});

test('página saindo é descartável e tem prioridade', () => {
    const r = classificarFalha(
        new TypeError('Load failed'),
        ambiente({ paginaSaindo: true, navigator: { onLine: false } })
    );
    assert.equal(r.causa, 'navegando');
    assert.equal(r.descartavel, true);
});

test('AbortError é timeout', () => {
    const erro = new Error('abortado');
    erro.name = 'AbortError';
    assert.equal(classificarFalha(erro, ambiente()).causa, 'timeout');
});

test('AxiosError ERR_NETWORK é falha de rede', () => {
    const erro = Object.assign(new Error('Network Error'), { code: 'ERR_NETWORK' });
    assert.equal(classificarFalha(erro, ambiente()).causa, 'desconhecida');
});

test('403 do axios é http_403 com orientação de recarregar', () => {
    const erro = Object.assign(new Error('Request failed with status code 403'), { response: { status: 403 } });
    const r = classificarFalha(erro, ambiente());
    assert.equal(r.causa, 'http_403');
    assert.equal(r.descartavel, false);
    assert.match(r.mensagem, /Recarregue a página/);
    assert.equal(r.detalhes.http_status, 403);
});

test('status 5xx e outros 4xx são classificados', () => {
    assert.equal(classificarFalha(Object.assign(new Error('x'), { status: 502 }), ambiente()).causa, 'http_5xx');
    assert.equal(classificarFalha(Object.assign(new Error('x'), { status: 404 }), ambiente()).causa, 'http');
});

test('erro de programação não vira falha de rede', () => {
    assert.equal(classificarFalha(new RangeError('boom'), ambiente()).causa, 'outro');
});

test('detalhes carregam sinais de conexão', () => {
    const r = classificarFalha(
        new TypeError('Load failed'),
        ambiente({ navigator: { onLine: true, connection: { effectiveType: '3g', rtt: 400, downlink: 1.2 } } })
    );
    assert.deepEqual([r.detalhes.tipo_conexao, r.detalhes.rtt, r.detalhes.downlink], ['3g', 400, 1.2]);
});

test('mensagem padrão para causa desconhecida', () => {
    assert.match(mensagemParaUsuario('desconhecida'), /conectar ao servidor/);
});

const resposta = (status) => ({ ok: status >= 200 && status < 300, status });

test('buscarComRetry repete após falha de rede e devolve a resposta', async () => {
    let chamadas = 0;
    const fetchFn = async () => {
        chamadas += 1;
        if (chamadas === 1) throw new TypeError('Load failed');
        return resposta(200);
    };
    const res = await buscarComRetry('/x', { fetchFn, esperaMs: 0 });
    assert.equal(res.status, 200);
    assert.equal(chamadas, 2);
});

test('buscarComRetry repete em 5xx', async () => {
    const respostas = [resposta(503), resposta(200)];
    const res = await buscarComRetry('/x', { fetchFn: async () => respostas.shift(), esperaMs: 0 });
    assert.equal(res.status, 200);
});

test('buscarComRetry não repete 4xx e expõe status', async () => {
    let chamadas = 0;
    await assert.rejects(
        buscarComRetry('/x', {
            fetchFn: async () => {
                chamadas += 1;
                return resposta(403);
            },
            esperaMs: 0,
        }),
        (erro) => erro.status === 403
    );
    assert.equal(chamadas, 1);
});

test('buscarComRetry desiste após esgotar as tentativas', async () => {
    let chamadas = 0;
    await assert.rejects(
        buscarComRetry('/x', {
            fetchFn: async () => {
                chamadas += 1;
                throw new TypeError('Load failed');
            },
            tentativas: 3,
            esperaMs: 0,
        }),
        TypeError
    );
    assert.equal(chamadas, 3);
});

test('buscarComRetry aborta por timeout', async () => {
    const fetchFn = (url, { signal }) =>
        new Promise((_, rejeitar) => {
            signal.addEventListener('abort', () => rejeitar(Object.assign(new Error('abort'), { name: 'AbortError' })));
        });
    await assert.rejects(
        buscarComRetry('/x', { fetchFn, tentativas: 1, timeoutMs: 10 }),
        (erro) => erro.name === 'AbortError'
    );
});

// DOM mínimo para o aviso.
const criarDoc = () => {
    const elementos = [];
    const novo = (tag) => ({
        tag,
        children: [],
        listeners: {},
        attrs: {},
        style: {},
        removido: false,
        setAttribute(k, v) {
            this.attrs[k] = v;
        },
        appendChild(c) {
            this.children.push(c);
        },
        addEventListener(ev, fn) {
            this.listeners[ev] = fn;
        },
        remove() {
            this.removido = true;
        },
    });
    const doc = {
        body: { appendChild: (el) => elementos.push(el) },
        createElement: novo,
        getElementById: () => elementos.find((e) => e.id === 'aviso-rede' && !e.removido) || null,
    };
    return { doc, elementos };
};

test('mostrarAviso exibe texto e botão que chama a nova tentativa', () => {
    const { doc, elementos } = criarDoc();
    let tentou = 0;
    const caixa = mostrarAviso('Falhou', {
        doc,
        aoTentarNovamente: () => {
            tentou += 1;
        },
    });
    assert.equal(elementos.length, 1);
    assert.equal(caixa.attrs.role, 'status');
    assert.equal(caixa.children[0].textContent, 'Falhou');
    const botao = caixa.children.find((c) => c.textContent === 'Tentar novamente');
    botao.listeners.click();
    assert.equal(tentou, 1);
    assert.equal(caixa.removido, true);
});

test('mostrarAviso substitui o aviso anterior', () => {
    const { doc, elementos } = criarDoc();
    mostrarAviso('um', { doc });
    mostrarAviso('dois', { doc });
    assert.equal(elementos[0].removido, true);
    assert.equal(elementos[1].removido, false);
});

// sentry-init.js: sentryReport aplica tags e respeita `descartar`.
const carregarSentryInit = () => {
    const capturados = [];
    const escopo = {
        extras: {},
        tags: {},
        setExtras(e) {
            Object.assign(this.extras, e);
        },
        setTags(t) {
            Object.assign(this.tags, t);
        },
    };
    const window = {
        Sentry: {
            init() {},
            withScope(fn) {
                fn(escopo);
            },
            captureException(e) {
                capturados.push(e);
                return 'f546d77d179c499ea0b9c0a1d2e3f405';
            },
        },
    };
    const config = '{"dsn":"https://k@s/1","environment":"t","release":"1","sampleRate":1}';
    const document = { getElementById: () => ({ textContent: config }) };
    vm.runInNewContext(fs.readFileSync(path.join(JS_DIR, 'sentry-init.js'), 'utf8'), { window, document, console });
    return { window, capturados, escopo };
};

test('sentryReport envia com tags e extras', () => {
    const { window, capturados, escopo } = carregarSentryInit();
    const erro = new Error('x');
    window.sentryReport(erro, { mensagem: 'm', tags: { causa_falha: 'timeout' }, descartar: false });
    assert.deepEqual(capturados, [erro]);
    assert.deepEqual(escopo.tags, { causa_falha: 'timeout' });
    assert.equal(escopo.extras.mensagem, 'm');
    assert.equal('tags' in escopo.extras, false);
});

test('sentryReport devolve o ID do evento para exibir ao usuário', () => {
    const { window } = carregarSentryInit();
    assert.equal(window.sentryReport(new Error('x'), {}), 'f546d77d179c499ea0b9c0a1d2e3f405');
});

test('sentryReport não envia quando descartar e não devolve ID', () => {
    const { window, capturados } = carregarSentryInit();
    assert.equal(window.sentryReport(new Error('x'), { descartar: true }), undefined);
    assert.equal(capturados.length, 0);
});

test('comCodigo acrescenta o código do evento à mensagem', () => {
    assert.equal(comCodigo('Falhou.', 'abc123'), 'Falhou. (Código do erro: abc123)');
});

test('comCodigo mantém a mensagem sem ID de evento', () => {
    assert.equal(comCodigo('Falhou.', undefined), 'Falhou.');
});

test('mostrarAviso deixa o texto selecionável para copiar o código', () => {
    const { doc } = criarDoc();
    const caixa = mostrarAviso(comCodigo('Falhou.', 'abc123'), { doc });
    assert.equal(caixa.children[0].style.userSelect, 'all');
    assert.match(caixa.children[0].textContent, /abc123/);
});

test('sentryReport anexa status e url de erro axios', () => {
    const { window, escopo } = carregarSentryInit();
    const erro = Object.assign(new Error('x'), { response: { status: 403, config: { url: '/curso/2/4023/enrol/' } } });
    window.sentryReport(erro, {});
    assert.equal(escopo.extras.http_status, 403);
    assert.equal(escopo.extras.http_url, '/curso/2/4023/enrol/');
});
