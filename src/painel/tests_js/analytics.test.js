// Testes do helper de analytics. Executar com: node --test src/painel/tests_js/analytics.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const JS_DIR = path.join(__dirname, '..', '..', 'theme_ifrn25', 'static', 'theme', 'ifrn25', 'js');
const { lerConfig, track, trackErroJs, cortar } = require(path.join(JS_DIR, 'analytics.js'));

const limpar = () => {
    delete globalThis.gtag;
    delete globalThis.clarity;
};

test('lerConfig sem elemento ou com JSON inválido devolve objeto vazio', () => {
    assert.deepEqual(lerConfig({ getElementById: () => null }), {});
    const original = console.error;
    console.error = () => {};
    try {
        assert.deepEqual(lerConfig({ getElementById: () => ({ textContent: '{x' }) }), {});
    } finally {
        console.error = original;
    }
});

test('lerConfig lê as chaves do tema', () => {
    const doc = { getElementById: () => ({ textContent: '{"gtag":"G-1","clarity":"abc"}' }) };
    assert.deepEqual(lerConfig(doc), { gtag: 'G-1', clarity: 'abc' });
});

test('track sem GA/Clarity carregados não lança erro', () => {
    limpar();
    assert.doesNotThrow(() => track('x', { a: 1 }));
});

test('track envia ao GA e ao Clarity', () => {
    limpar();
    const chamadas = [];
    globalThis.gtag = (...a) => chamadas.push(['gtag', ...a]);
    globalThis.clarity = (...a) => chamadas.push(['clarity', ...a]);
    track('modal_abrir', { tipo: 'help' });
    assert.deepEqual(chamadas, [['gtag', 'event', 'modal_abrir', { tipo: 'help' }], ['clarity', 'event', 'modal_abrir']]);
    limpar();
});

test('trackErroJs marca o Clarity e corta a mensagem em 100 caracteres', () => {
    limpar();
    const chamadas = [];
    globalThis.clarity = (...a) => chamadas.push(a);
    trackErroJs('error', 'x'.repeat(300));
    assert.deepEqual(chamadas[0], ['event', 'js_error']);
    assert.deepEqual(chamadas[1], ['set', 'js_error', 'error']);
    assert.equal(chamadas[2][1], 'js_error_msg');
    assert.equal(chamadas[2][2].length, 100);
    limpar();
});

test('cortar trata nulo', () => {
    assert.equal(cortar(null), '');
});
