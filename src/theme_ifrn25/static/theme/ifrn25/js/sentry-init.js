// Inicializa o Sentry no navegador somente se o Django expôs a configuração
// (SENTRY_JS_DSN). Sem ela, `window.sentryReport` é um no-op.
(function () {
    window.sentryReport = function () {
        return undefined;
    };

    const el = document.getElementById('sentry-js-config');
    if (!el || !window.Sentry) {
        return;
    }

    let config;
    try {
        config = JSON.parse(el.textContent);
    } catch (e) {
        console.error('Configuração do Sentry inválida:', e);
        return;
    }

    // Nada que venha da pasta `vendors` deve ser enviado.
    const VENDORS = /\/vendors\//;
    const veioDeVendors = (event) =>
        (event.exception?.values || []).some((valor) =>
            (valor.stacktrace?.frames || []).some((frame) => VENDORS.test(frame.filename || ''))
        );

    window.Sentry.init({
        dsn: config.dsn,
        environment: config.environment,
        release: config.release,
        sampleRate: config.sampleRate,
        denyUrls: [VENDORS],
        beforeSend(event) {
            return veioDeVendors(event) ? null : event;
        },
    });

    // Registra no Sentry um erro tratado (ex.: em um catch), com contexto extra.
    // `context.tags` vira tags do evento; `context.descartar` impede o envio
    // (falhas que não indicam defeito, como o usuário navegando para outra página).
    // Retorna o ID do evento no Sentry (ou undefined se nada foi enviado), para
    // mostrar ao usuário e rastrear o caso caso ele abra um chamado.
    window.sentryReport = function (error, context) {
        const { tags, descartar, ...extras } = context || {};
        if (descartar) {
            return undefined;
        }
        let eventId;
        try {
            window.Sentry.withScope((scope) => {
                scope.setExtras(extras);
                if (tags) {
                    scope.setTags(tags);
                }
                const resp = error && error.response;
                if (resp) {
                    scope.setExtras({ http_status: resp.status, http_url: resp.config && resp.config.url });
                }
                eventId = window.Sentry.captureException(error);
            });
        } catch (e) {
            console.error('Falha ao enviar erro ao Sentry:', e);
        }
        return eventId;
    };
})();
