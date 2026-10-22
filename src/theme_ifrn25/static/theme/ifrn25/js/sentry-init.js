// Inicializa o Sentry no navegador somente se o Django expôs a configuração
// (SENTRY_JS_DSN). Sem ela, `window.sentryReport` é um no-op.
(function () {
    window.sentryReport = function () {};

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
    window.sentryReport = function (error, context) {
        try {
            window.Sentry.withScope((scope) => {
                if (context) {
                    scope.setExtras(context);
                }
                const resp = error && error.response;
                if (resp) {
                    scope.setExtras({ http_status: resp.status, http_url: resp.config && resp.config.url });
                }
                window.Sentry.captureException(error);
            });
        } catch (e) {
            console.error('Falha ao enviar erro ao Sentry:', e);
        }
    };
})();
