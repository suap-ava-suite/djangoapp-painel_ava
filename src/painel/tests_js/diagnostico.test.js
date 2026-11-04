// Testes das funções puras do diagnóstico. Executar com: node --test src/painel/tests_js/diagnostico.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const JS_DIR = path.join(__dirname, '..', '..', 'theme_ifrn25', 'static', 'theme', 'ifrn25', 'js');
const { urlPara, paramsConsulta, paramsAutoinscricao, formatarData } = require(path.join(JS_DIR, 'diagnostico.js'));

test('urlPara codifica o username', () => {
    assert.equal(urlPara('/diagnostico/__username__/usuario/', 'a b/c'), '/diagnostico/a%20b%2Fc/usuario/');
});

test('paramsConsulta só tem categorias e contagens', () => {
    const params = paramsConsulta({
        username: '20201234',
        existe_no_painel: true,
        usuario: { nome: 'Fulano' },
        ambientes: [{ status: 'ok' }, { status: 'sem_conta' }, { status: 'endpoint_indisponivel' }, { status: 'erro' }],
    });
    assert.deepEqual(params, { resultado: 'encontrado', ambientes_com_conta: 1, ambientes_indisponiveis: 2 });
    assert.ok(!JSON.stringify(params).includes('20201234'));
    assert.ok(!JSON.stringify(params).includes('Fulano'));
});

test('paramsConsulta com usuário inexistente', () => {
    assert.equal(paramsConsulta({ existe_no_painel: false, ambientes: [] }).resultado, 'nao_encontrado');
});

test('paramsAutoinscricao conta cursos e escolhe o motivo mais frequente', () => {
    const params = paramsAutoinscricao({
        username: 'aluno',
        ambientes: [
            { cursos: [{ atende: true, motivo: 'ok', fullname: 'Curso secreto', regra: "x == 'y'" }, { atende: false, motivo: 'regra_falsa' }] },
            { cursos: [{ atende: false, motivo: 'regra_falsa' }, { atende: false, motivo: 'erro_avaliacao' }] },
        ],
    });
    assert.deepEqual(params, { cursos_total: 4, cursos_atende: 1, cursos_nao_atende: 3, motivo_principal: 'regra_falsa' });
    assert.ok(!JSON.stringify(params).includes('Curso secreto'));
});

test('paramsAutoinscricao sem cursos', () => {
    assert.equal(paramsAutoinscricao({ ambientes: [] }).motivo_principal, 'nenhum');
});

test('formatarData trata nulo e timestamp do Moodle', () => {
    assert.equal(formatarData(0), 'nunca');
    assert.equal(formatarData(null), 'nunca');
    assert.notEqual(formatarData(1790000000), '—');
    assert.equal(formatarData('xyz'), '—');
});

const { trechosDaRegra, formatarValor } = require(path.join(JS_DIR, 'diagnostico.js'));

test('trechosDaRegra marca cada comparação na ordem do texto', () => {
    const regra = "a == 1 and $any([m['x'] == 'a' and m['y'] == 2 for m in outras_matriculas])";
    const trechos = trechosDaRegra(regra, [
        { atomo: 'a == 1', atendido: true },
        { atomo: "m['x'] == 'a'", atendido: false },
        { atomo: "m['y'] == 2", atendido: null },
        { atomo: 'não existe', atendido: true },
    ]);
    assert.equal(trechos.map((t) => t.texto).join(''), regra);
    assert.deepEqual(
        trechos.filter((t) => 'atendido' in t).map((t) => [t.texto, t.atendido]),
        [['a == 1', true], ["m['x'] == 'a'", false], ["m['y'] == 2", null]]
    );
});

test('trechosDaRegra sem linhas devolve a regra inteira', () => {
    assert.deepEqual(trechosDaRegra('x == 1', []), [{ texto: 'x == 1' }]);
});

test('formatarValor mostra aspas para revelar diferenças de grafia', () => {
    assert.equal(formatarValor('Técnico Integrado'), '"Técnico Integrado"');
    assert.equal(formatarValor(undefined), '—');
    assert.equal(formatarValor(true), 'true');
});
