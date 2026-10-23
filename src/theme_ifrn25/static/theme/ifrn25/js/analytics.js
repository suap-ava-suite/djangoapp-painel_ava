// Google Analytics (GA4) e Microsoft Clarity do tema ifrn25. Só carrega o que o Django
// expôs em `analytics-config` (IFRN25_GTAG_CODE / IFRN25_CLARITY_CODE). Sem configuração,
// `window.track` e `window.trackErroJs` são no-ops. Nunca envie dados pessoais.
// Script clássico: expõe `window.track` e, no Node, `module.exports` (para testes).
(function (raiz) {
    const MAX_MSG = 100;
    // Distingue o ifrn25 do ifrn23 quando os dois compartilham a mesma propriedade do GA4.
    const TEMA = 'ifrn25';

    const lerConfig = (doc) => {
        const el = doc && doc.getElementById('analytics-config');
        if (!el) {
            return {};
        }
        try {
            return JSON.parse(el.textContent) || {};
        } catch (e) {
            console.error('Configuração de analytics inválida:', e);
            return {};
        }
    };

    const carregarClarity = (w, d, id) => {
        (function (c, l, a, r, i, t, y) {
            c[a] = c[a] || function () { (c[a].q = c[a].q || []).push(arguments); };
            t = l.createElement(r); t.async = 1; t.src = 'https://www.clarity.ms/tag/' + i;
            y = l.getElementsByTagName(r)[0]; y.parentNode.insertBefore(t, y);
        })(w, d, 'clarity', 'script', id);
    };

    const carregarGtag = (w, d, id) => {
        w.dataLayer = w.dataLayer || [];
        w.gtag = w.gtag || function () { w.dataLayer.push(arguments); };
        w.gtag('js', new Date());
        w.gtag('set', 'user_properties', { tema: TEMA });
        w.gtag('config', id);
        const s = d.createElement('script');
        s.async = true;
        s.src = 'https://www.googletagmanager.com/gtag/js?id=' + encodeURIComponent(id);
        d.head.appendChild(s);
    };

    const cortar = (valor) => String(valor == null ? '' : valor).slice(0, MAX_MSG);

    // Envia o evento ao GA e ao Clarity (cada um só se estiver carregado).
    const track = (evento, params) => {
        try {
            if (typeof raiz.gtag === 'function') {
                raiz.gtag('event', evento, params || {});
            }
            if (typeof raiz.clarity === 'function') {
                raiz.clarity('event', evento);
            }
        } catch (e) {
            console.error('Falha ao enviar evento de analytics:', e);
        }
    };

    // Registra um erro de JS: evento no GA/Clarity e tags no Clarity para filtrar as gravações.
    const trackErroJs = (tipo, mensagem) => {
        const msg = cortar(mensagem);
        track('js_error', { tipo, mensagem: msg });
        try {
            if (typeof raiz.clarity === 'function') {
                raiz.clarity('set', 'js_error', tipo);
                raiz.clarity('set', 'js_error_msg', msg);
            }
        } catch (e) {
            console.error('Falha ao marcar erro de JS no Clarity:', e);
        }
    };

    const iniciar = (w, d) => {
        const config = lerConfig(d);
        if (config.clarity) {
            carregarClarity(w, d, config.clarity);
            w.clarity('set', 'tema', TEMA);
        }
        if (config.gtag) {
            carregarGtag(w, d, config.gtag);
        }
        w.addEventListener('error', (e) => {
            trackErroJs('error', e.message || 'script error');
        });
        w.addEventListener('unhandledrejection', (e) => {
            const r = e.reason;
            trackErroJs('promise', (r && r.message) || r || 'unhandled rejection');
        });
    };

    raiz.track = track;
    raiz.trackErroJs = trackErroJs;

    if (typeof document !== 'undefined' && raiz.addEventListener) {
        iniciar(raiz, document);
    }
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { lerConfig, track, trackErroJs, cortar };
    }
})(typeof window !== 'undefined' ? window : globalThis);
