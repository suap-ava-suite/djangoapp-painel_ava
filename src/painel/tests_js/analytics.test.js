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

test('paramsDoElemento converte data-track-* em parâmetros snake_case', () => {
    const { paramsDoElemento } = require(path.join(JS_DIR, 'analytics.js'));
    const el = { dataset: { track: 'x', trackDestino: 'suap', trackId_ambiente: '7', outro: 'ignorado' } };
    assert.deepEqual(paramsDoElemento(el), { destino: 'suap', id_ambiente: '7' });
    assert.deepEqual(paramsDoElemento({ dataset: { trackIdAmbiente: '3' } }), { id_ambiente: '3' });
});

test('lerPropriedades lê só preferências da página', () => {
    const { lerPropriedades } = require(path.join(JS_DIR, 'analytics.js'));
    const attrs = { 'data-zoom': '120' };
    const doc = {
        body: {
            classList: ['vlibras_active', 'color_mode_high_contrast', 'big_cursor'],
            getAttribute: (n) => attrs[n] || null,
        },
    };
    globalThis.INITIAL_SETTINGS = { menuPosition: 'bottom' };
    assert.deepEqual(lerPropriedades(doc, '1.1.068'), {
        color_mode: 'high_contrast',
        zoom_level: '120',
        menu_position: 'bottom',
        vlibras_ativo: true,
        app_version: '1.1.068',
    });
    delete globalThis.INITIAL_SETTINGS;
});

test('trackPropriedades envia ao GA e ao Clarity', () => {
    const { trackPropriedades } = require(path.join(JS_DIR, 'analytics.js'));
    limpar();
    const chamadas = [];
    globalThis.gtag = (...a) => chamadas.push(['gtag', ...a]);
    globalThis.clarity = (...a) => chamadas.push(['clarity', ...a]);
    trackPropriedades({ zoom_level: '150', vlibras_ativo: false });
    assert.deepEqual(chamadas, [
        ['gtag', 'set', 'user_properties', { zoom_level: '150', vlibras_ativo: false }],
        ['clarity', 'set', 'zoom_level', '150'],
        ['clarity', 'set', 'vlibras_ativo', 'false'],
    ]);
    limpar();
});
