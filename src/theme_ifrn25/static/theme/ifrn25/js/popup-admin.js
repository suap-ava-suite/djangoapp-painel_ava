// Exibe o Popup cadastrado no admin (painel.Popup), no mesmo critério do tema ifrn23:
// - sem registro no localStorage: exibe;
// - fechado sem responder ("Lembre-me depois"): volta a exibir depois de 12 h;
// - "Acessar agora": abre a URL e não exibe mais.
(function () {
    const REEXIBIR_APOS_MS = 12 * 3600 * 1000;
    const overlay = document.getElementById('popup-admin');
    if (!overlay) {
        return;
    }

    const chave = `modal${overlay.dataset.popupId}`;
    const url = overlay.dataset.popupUrl;

    const ler = () => {
        try {
            return localStorage.getItem(chave);
        } catch (e) {
            return null;
        }
    };
    const gravar = (valor) => {
        try {
            localStorage.setItem(chave, valor);
        } catch (e) {
            // Sem localStorage o popup apenas reaparece no próximo carregamento
        }
    };

    const registro = ler();
    if (registro === 'true') {
        return;
    }
    const ultimaVez = registro ? new Date(registro) : null;
    if (ultimaVez && !isNaN(ultimaVez) && Date.now() - ultimaVez < REEXIBIR_APOS_MS) {
        return;
    }

    const fechar = () => {
        overlay.classList.add('hidden');
        document.removeEventListener('keydown', aoPressionarTecla);
    };
    const lembrarDepois = () => {
        gravar(new Date().toISOString());
        fechar();
    };
    const acessarAgora = () => {
        gravar('true');
        fechar();
        // Só abre http(s), nunca esquemas como javascript:
        if (/^https?:\/\//i.test(url)) {
            window.open(url, '_blank', 'noopener');
        }
    };
    const aoPressionarTecla = (event) => {
        if (event.key === 'Escape') {
            lembrarDepois();
        }
    };

    document.getElementById('popup-admin-later').addEventListener('click', lembrarDepois);
    document.getElementById('popup-admin-access').addEventListener('click', acessarAgora);
    overlay.addEventListener('click', (event) => {
        if (event.target === overlay) {
            lembrarDepois();
        }
    });
    document.addEventListener('keydown', aoPressionarTecla);

    overlay.classList.remove('hidden');
    document.getElementById('popup-admin-access').focus();
})();
