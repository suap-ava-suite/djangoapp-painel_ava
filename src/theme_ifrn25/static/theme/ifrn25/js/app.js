import * as VueSelect from './vue-select.js';

// Registra o erro no console e o envia ao Sentry (no-op sem SENTRY_JS_DSN),
// etiquetado com a causa provável. Falhas que não são defeito nosso (usuário
// navegando, aba em segundo plano) são classificadas, mas não enviadas.
// Retorna a classificação ({ causa, mensagem, eventId, ... }) para uso na interface;
// `eventId` é o código do evento no Sentry, a ser mostrado ao usuário.
const reportJsError = (mensagem, error) => {
    console.error(mensagem, error);
    const falha = window.ErrosRede?.classificarFalha(error);
    const eventId = window.sentryReport?.(error, {
        mensagem,
        ...falha?.detalhes,
        descartar: falha?.descartavel,
        tags: falha ? { causa_falha: falha.causa } : undefined,
    });
    return { ...falha, eventId };
};

const getSalasIniciais = () => {
    const nomesAdmin = window.PAGE_CONFIG?.nomesAbas || {};
    const salas = {};
    const keys = Object.keys(nomesAdmin);

    if (keys.length > 0) {
        keys.forEach(key => {
            if (nomesAdmin[key].sempreVisivel) {
                salas[key] = [];
            }
        });
    } else {
        salas['diarios'] = [];
        salas['coordenacoes'] = [];
    }
    return salas;
};

const app = Vue.createApp({
    delimiters: ["[[", "]]"],
    components: {
        'v-select': VueSelect.default,
    },
    data() {
        return {
            enableFilters: window.PAGE_CONFIG?.enableFilters ?? true,
            isBottom: window.INITIAL_SETTINGS.menuPosition === 'bottom',
            sidebarContracted: false,
            modalOpen: false,
            accessibilityModalOpen: false,
            helpModalOpen: false,
            notificationsModalOpen: false,
            messagesModalOpen: false,
            filterModalOpen: false,
            profileModalOpen: false,
            modalHeaderIcons: {
                accessibility: 'fa-universal-access',
                help: 'fa-question-circle',
                notifications: 'fa-bell',
                messages: 'fa-comment',
                filter: 'fa-filter',
                profile: 'fa-user',
            },
            modalHeaderIcon: '',
            modalType: '',
            modalTitle: '',
            activeTab: 0,
            tabs: [
                { originalIndex: 0, key: 'diarios', desktop: 'Meus Diários', mobile: 'Diários' },
                { originalIndex: 1, key: 'coordenacoes', desktop: 'Salas de Coordenação', mobile: 'Coordenações' },
                { originalIndex: 2, key: 'praticas', desktop: 'Práticas', mobile: 'Práticas' },
                { originalIndex: 3, key: 'reutilizaveis', desktop: 'Reutilizar', mobile: 'Reutilizar' },
                { originalIndex: 4, key: 'autoinscricoes', desktop: 'Cursos com Autoinscrição', mobile: 'Autoinscrições' },
            ],
            filters: {
                situacao: 'inprogress',
                semestre: null,
                periodo: null,
                modulo: null,
                disciplina: null,
                curso: null,
                ambiente: null,
                query: null,
            },

            splideInstance: null,
            selectedMessageOption: 'all',
            messageOptions: [
                { label: 'Todos', value: 'all' },
                { label: 'Não lidas', value: 'unread' },
                { label: 'Grupos', value: 'groups' },
                { label: 'Favoritos', value: 'favorites' },
                { label: 'Privado', value: 'private' }
            ],
            preferences: {
                dyslexia_friendly: false,
                big_cursor: false,
                vlibras_active: true,
                highlight_links: false,
                stop_animations: false,
                hidden_illustrative_image: false,
                remove_justify: false,
                high_line_height: false,
                zoom_level: '100',
                zoom_options: ['100', '120', '130', '150', '160'],
                color_mode: 'default',
                color_mode_options: ['default', 'high_contrast', 'low_contrast', 'colorblind', 'grayscale'],
            },
            messages: [
                // { id: 1, receiver: 'Ronaldo', sender: '', content: 'Conteúdo da mensagem 1', date: '2023-03-25 12:00', read: false, favorite: true, group: '', img: 'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcS8E7wlGmOb1_0GI4vqlvieVWlGdkMW5Mv0XQ&s' },
                // { id: 2, receiver: '', sender: 'Messi', content: 'Conteúdo da mensagem 22222222222222222222222222222222222222222222222222', date: '2023-01-02 14:00', read: true, favorite: true, group: 'Grupo A', img: 'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSxLoJONSCCuN_JBwM_xVD5hloPBf4pHB9R7A&s' },
                // { id: 3, receiver: 'Neymar', sender: '', content: 'Conteúdo da mensagem 3', date: '2023-01-03 16:00', read: false, favorite: false, group: 'Grupo B', img: 'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSNMnJ3i8BARfyzD9fxQ9GvorEDF1gTrZqzrA&s' },
                // { id: 4, receiver: '', sender: 'Cristiano Ronaldo', content: 'Conteúdo da mensagem 44444444444444', date: '2023-01-04 18:00', read: true, favorite: true, group: '', img: 'https://img.a.transfermarkt.technology/portrait/big/8198-1694609670.jpg?lm=1' },
                // { id: 5, receiver: 'Zidane', sender: '', content: 'Conteúdo da mensagem 5', date: '2023-03-25 20:00', read: false, favorite: false, group: 'Grupo A', img: 'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRoSDG52Efy_SkQKqp9tTaS46NaaZCNEX2LJQ&s' },
                // { id: 6, receiver: 'Ronaldinho', sender: '', content: 'Conteúdo da mensagem 6666666666666', date: '2023-03-25 12:00', read: true, favorite: true, group: 'Grupo A', img: 'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSioEdBrFFM0iW0f6uhegsUMeMptl48GSdOeQ&s' },
            ],
            messageSearchQuery: '',
            notifications: [
                // { id: 1, title: 'Notificação 1', date: '2025-03-25 12:00', link: '#' },
                // { id: 2, title: 'Notificação 2', date: '2025-01-02 14:00', link: '#' },
                // { id: 3, title: 'Notificação 3', date: '2025-01-03 16:00', link: '#' },
                // { id: 4, title: 'Notificação 4', date: '2025-01-04 18:00', link: '#' },
                // { id: 5, title: 'Notificação 5', date: '2025-03-25 20:00', link: '#' },
                // { id: 6, title: 'Notificação 6', date: '2025-03-21 12:00', link: '#' },
                // { id: 7, title: 'Notificação 9', date: '2025-03-25 12:00', link: '#' },
            ],

            periodos: [],
            modulos: [],
            semestres: [],
            situacoes: [
                { label: "Diários em andamento", id: "inprogress" },
                { label: "Diários a iniciar", id: "future" },
                { label: "Encerrados pelo professor", id: "past" },
                { label: "Meus diários favoritos", id: "favourites" },
                { label: "Todos os diários (lento)", id: "allincludinghidden" },
            ],
            disciplinas: [],
            cursos: [],
            ambientes: [],
            salasPorCategoria: getSalasIniciais(), // Inicializado dinamicamente via banco ou fallback
            activeTabKey: 'diarios',
            loading: true,
            isTakingLong: false,
            loadingTimeoutId: null,
        };
    },
    watch: {
        messagesModalOpen(newVal) {
            if (newVal) {
                this.$nextTick(() => {
                    this.initSplide();
                    this.splideInstance.refresh();
                });
            } else {
                if (this.splideInstance) {
                    this.splideInstance.destroy();
                }
            }
        },
        filters: {
            handler() {
                // this.filterCards();
                console.log('Filters changed:', this.filters);
                localStorage.setItem('filters', JSON.stringify(this.filters));
            },
            deep: true // Observa mudanças profundas no objeto
        }
    },
    computed: {
        visibleTabs() {
            // Definições padrão e lógicas de visibilidade caso não venha do Django Admin
            const configPadrao = {
                diarios: { desktop: 'Meus Diários', mobile: 'Diários', order: 1, sempreVisivel: true },
                coordenacoes: { desktop: 'Salas de Coordenação', mobile: 'Coordenações', order: 2, sempreVisivel: true },
                praticas: { desktop: 'Práticas', mobile: 'Práticas', order: 3 },
                reutilizaveis: { desktop: 'Reutilizar', mobile: 'Reutilizar', order: 4 },
                autoinscricoes: { desktop: 'Cursos com Autoinscrição', mobile: 'Autoinscrições', order: 5 }
            };

            const nomesAdmin = window.PAGE_CONFIG?.nomesAbas || {};

            let tabs = [];

            Object.keys(this.salasPorCategoria).forEach(key => {
                const itens = this.salasPorCategoria[key] || [];

                // Mescla as configurações (Admin -> Padrão -> Fallback dinâmico)
                const config = nomesAdmin[key] || configPadrao[key] || {
                    desktop: key.charAt(0).toUpperCase() + key.slice(1),
                    mobile: key.charAt(0).toUpperCase() + key.slice(1),
                    order: 99,
                    sempreVisivel: false
                };

                // Mostra se tiver item OU se for configurada para sempre aparecer (como Diários)
                if (itens.length > 0 || config.sempreVisivel) {
                    tabs.push({
                        key: key,
                        desktop: config.desktop,
                        mobile: config.mobile,
                        order: config.order
                    });
                }
            });

            return tabs.sort((a, b) => a.order - b.order);
        },

        filteredMessages() {
            const searchQuery = this.messageSearchQuery.toLowerCase();

            return this.messages.filter(msg => {
                // Filtro por tipo de mensagem
                let matchesType = false;
                switch (this.selectedMessageOption) {
                    case 'all': matchesType = true; break;
                    case 'unread': matchesType = !msg.read; break;
                    case 'groups': matchesType = msg.group !== ''; break;
                    case 'favorites': matchesType = msg.favorite; break;
                    case 'private': matchesType = msg.group === ''; break;
                    default: matchesType = true;
                }

                // Filtro por busca textual
                const matchesSearch = !searchQuery ||
                    (msg.sender && msg.sender.toLowerCase().includes(searchQuery)) ||
                    (msg.receiver && msg.receiver.toLowerCase().includes(searchQuery));

                return matchesType && matchesSearch;
            });
        },
        activeFilters() {
            const filterTypes = [
                { key: 'situacao', options: this.situacoes, icon: 'fa-book' },
                { key: 'semestre', options: this.semestres, icon: 'fa-calendar-days' },
                { key: 'periodo', options: this.periodos, icon: 'fa-calendar-week' },
                { key: 'modulo', options: this.modulos, icon: 'fa-calendar-day' },
                { key: 'disciplina', options: this.disciplinas, icon: 'fa-newspaper' },
                { key: 'curso', options: this.cursos, icon: 'cursos' },
                { key: 'ambiente', options: this.ambientes, icon: 'ambientes' }
            ];
            return filterTypes.reduce((acc, { key, options, icon }) => {
                const value = this.filters[key];
                if (value) {
                    const option = options.find(o => o.id === value);
                    if (option) {
                        acc.push({
                            type: key,
                            label: option.label,
                            value: value,
                            icon: icon
                        });
                    }
                }
                return acc;
            }, []);
        }
    },
    mounted() {
        this.clearGauge();
        this.getPreferences();
        if (this.enableFilters) {
            this.loadFilters();
            this.filterCards();
        } else {
            this.loading = false;
        }
        this.sidebarContracted = this.isMobile();
    },
    methods: {
        getPreferences() {
            if (document.body.classList.contains('dyslexia_friendly')) {
                this.preferences.dyslexia_friendly = true;
            }
            if (document.body.classList.contains('big_cursor')) {
                this.preferences.big_cursor = true;
            }
            if (!document.body.classList.contains('vlibras_active')) {
                this.preferences.vlibras_active = false;
            }
            if (document.body.classList.contains('highlight_links')) {
                this.preferences.highlight_links = true;
            }
            if (document.body.classList.contains('stop_animations')) {
                this.preferences.stop_animations = true;
            }
            if (document.body.classList.contains('hidden_illustrative_image')) {
                this.preferences.hidden_illustrative_image = true;
            }
            if (document.body.classList.contains('remove_justify')) {
                this.preferences.remove_justify = true;
            }
            if (document.body.classList.contains('high_line_height')) {
                this.preferences.high_line_height = true;
            }

            const zoom = document.body.getAttribute('data-zoom');
            if (zoom) {
                this.preferences.zoom_level = zoom;
            }

            const bodyClassList = document.body.classList;
            const colorModeClass = [...bodyClassList].find(c => c.startsWith('color_mode_'));

            if (colorModeClass) {
                this.preferences.color_mode = colorModeClass.replace('color_mode_', '');
            }
        },
        async savePosition() {
            const pos = this.isBottom ? 'bottom' : 'top';
            const app = document.getElementById('app');
            try {
                await axios.post(
                    '/settings/menu-position/',
                    new URLSearchParams({ position: pos }),
                    { headers: { 'X-CSRFToken': this.getCsrfToken() } }
                );
                app.classList.toggle('menu-bottom', this.isBottom);
            } catch (err) {
                reportJsError('Não foi possível salvar a posição:', err);
            }
        },
        getCsrfToken() {
            const token = document.cookie
                .split(';')
                .map(c => c.trim())
                .find(c => c.startsWith('csrftoken='));

            return token ? token.split('=')[1] : '';
        },
        initSplide() {
            if (this.splideInstance) {
                this.splideInstance.destroy();
            }
            this.$nextTick(() => {
                if (typeof Splide !== 'undefined') {
                    this.splideInstance = new Splide('.splide', {
                        type: 'slide',
                        perPage: 1,
                        pagination: false,
                        autoWidth: true,
                        arrows: false,
                        drag: 'free',
                        wheel: true,
                        releaseWheel: true,
                        speed: 600,
                        wheelSleep: 300,
                        wheelMinThreshold: 20,
                        gap: '5px',
                        breakpoints: {
                            768: {
                                perPage: 2,
                            },
                            480: {
                                perPage: 1,
                            }
                        }
                    }).mount();
                }
            });
        },
        formatDateForMessages(dateString) {
            const messageDate = new Date(dateString);
            const today = new Date();
            if (messageDate.toDateString() === today.toDateString()) {
                return messageDate.toLocaleTimeString('pt-BR', {
                    hour: '2-digit',
                    minute: '2-digit'
                });
            }
            return messageDate.toLocaleDateString('pt-BR', {
                day: '2-digit',
                month: '2-digit',
                year: 'numeric'
            });
        },
        formatDateForNotifications(dateString) {
            const notificationDate = new Date(dateString);
            const now = new Date();
            const diffInMilliseconds = now - notificationDate;
            const diffInMinutes = Math.floor(diffInMilliseconds / (1000 * 60));
            const diffInHours = Math.floor(diffInMinutes / 60);
            const diffInDays = Math.floor(diffInHours / 24);
            if (diffInDays > 0) return `${diffInDays} dias atrás`;
            if (diffInHours > 0) return `${diffInHours} horas atrás`;
            return `${diffInMinutes} minutos atrás`;
        },
        selectMessageOption(value) {
            this.selectedMessageOption = value;
            if (this.splideInstance) {
                this.splideInstance.refresh();
            }
        },
        isMobile() {
            return window.innerWidth < 768
        },
        toggleModalWithContent(type) {
            if (this.isMobile()) {
                this.closeSidebar();
            }
            if (this.modalOpen && this.modalType === type) {
                this.modalType = null;
                this.modalOpen = false;
                return;
            }
            if (this.modalOpen && this.modalType !== type) {
                this.modalOpen = false;
                setTimeout(() => {
                    this.modalType = type;
                    this.modalTitle = this.getModalTitle(type);
                    this.modalHeaderIcon = this.modalHeaderIcons[type];
                    this.modalOpen = true;
                }, 200);
                return;
            }
            this.modalType = type;
            this.modalTitle = this.getModalTitle(type);
            this.modalHeaderIcon = this.modalHeaderIcons[type];
            this.modalOpen = true;

        },
        getModalTitle(type) {
            switch (type) {
                case 'accessibility':
                    this.accessibilityModalOpen = true;
                    this.helpModalOpen = false;
                    this.notificationsModalOpen = false;
                    this.messagesModalOpen = false;
                    this.filterModalOpen = false;
                    this.profileModalOpen = false;
                    return 'Acessibilidade';
                case 'help':
                    this.helpModalOpen = true;
                    this.accessibilityModalOpen = false;
                    this.notificationsModalOpen = false;
                    this.messagesModalOpen = false;
                    this.filterModalOpen = false;
                    this.profileModalOpen = false;
                    return 'Ajuda';
                case 'notifications':
                    this.notificationsModalOpen = true;
                    this.accessibilityModalOpen = false;
                    this.helpModalOpen = false;
                    this.messagesModalOpen = false;
                    this.filterModalOpen = false;
                    this.profileModalOpen = false;
                    return 'Notificações';
                case 'messages':
                    this.messagesModalOpen = true;
                    this.accessibilityModalOpen = false;
                    this.helpModalOpen = false;
                    this.notificationsModalOpen = false;
                    this.filterModalOpen = false;
                    this.profileModalOpen = false;
                    return 'Mensagens';
                case 'filter':
                    this.filterModalOpen = true;
                    this.accessibilityModalOpen = false;
                    this.helpModalOpen = false;
                    this.notificationsModalOpen = false;
                    this.messagesModalOpen = false;
                    this.profileModalOpen = false;
                    return 'Filtros';
                case 'profile':
                    this.profileModalOpen = true;
                    this.accessibilityModalOpen = false;
                    this.helpModalOpen = false;
                    this.notificationsModalOpen = false;
                    this.messagesModalOpen = false;
                    this.filterModalOpen = false;
                    return 'Menu do Usuário';
                default:
                    return '';
            }
        },
        toggleSidebar() {
            if (this.isMobile()) {
                this.closeSidebarModal();
            }
            this.sidebarContracted = !this.sidebarContracted
        },
        closeSidebar() {
            this.sidebarContracted = true;
        },
        closeSidebarModal() {
            this.modalOpen = false;
            this.modalType = '';
            this.modalTitle = '';
            this.modalHeaderIcon = '';
        },
        closeSidebarAndModal() {
            this.closeSidebar();
            this.closeSidebarModal();
        },
        setActiveTab(key) {
            this.activeTabKey = key;
        },
        getNumberCourses(categoryKey) {
            const category = this.salasPorCategoria[categoryKey];
            if (category && Array.isArray(category)) {
                return category.length;
            }
            return 0;
        },
        async filterCards(exibirLoading = true) {
            // Modal fecha ao fazer busca no mobile
            if (this.isMobile()) {
                this.closeSidebarModal();
            }

            if (exibirLoading) {
                this.loading = true;
                this.isTakingLong = false;
                if (this.loadingTimeoutId) clearTimeout(this.loadingTimeoutId);
                this.loadingTimeoutId = setTimeout(() => {
                    this.isTakingLong = true;
                }, 8000);
            }

            try {
                const params = new URLSearchParams({
                    q: this.filters.query || "",
                    situacao: this.filters.situacao,
                    semestre: this.filters.semestre || "",
                    disciplina: this.filters.disciplina || "",
                    curso: this.filters.curso || "",
                    ambiente: this.filters.ambiente || "",
                });

                const res = await fetch(`/api/v1/diarios/?${params.toString()}`);
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();

                this.handleFilterResponse(data);
                this.loadProgress();
            } catch (error) {
                reportJsError("Error fetching data:", error);
                this.diarios = [];
            } finally {
                if (exibirLoading) {
                    this.loading = false;
                    if (this.loadingTimeoutId) clearTimeout(this.loadingTimeoutId);
                    this.isTakingLong = false;
                }
            }
        },

        mapCardData(curso) {
            return {
                id: curso.id,
                fullname: curso.fullname,
                shortname: curso.shortname ? this.changeShortnameStyle(curso.shortname) : '',
                isfavourite: curso.isfavourite || false,
                environment: curso.ambiente ? curso.ambiente.titulo : '',
                ambiente_id: curso.ambiente ? curso.ambiente.id : null,
                hasprogress: false,
                progress: null,
                progress_loading: true,
                visible: curso.visible == 1 || curso.visible === true,
                can_set_visibility: curso.can_set_visibility || 0,
                url: curso.viewurl || curso.url || '',
                // Específicos de autoinscrição (não quebram se não existirem nos outros)
                summary: curso.summary || '',
                is_enrolled: curso.is_enrolled || false,
                details_url: curso.details_url || ''
            };
        },

        handleFilterResponse(data) {
            const chavesDeFiltro = ['periodos', 'semestres', 'disciplinas', 'cursos', 'ambientes', 'modulos'];

            this.salasPorCategoria = getSalasIniciais();

            Object.keys(data).forEach(key => {
                if (chavesDeFiltro.includes(key)) {
                    // Preenche os selects de filtro ignorando o primeiro item vazio se houver
                    if (Array.isArray(data[key])) {
                        this[key] = (data[key][0]?.id === "") ? data[key].slice(1) : data[key];
                    }
                } else {
                    // Se não é filtro, assumimos que é uma lista de cursos/salas
                    if (Array.isArray(data[key])) {
                        this.salasPorCategoria[key] = data[key].map(curso => this.mapCardData(curso));
                    }
                }
            });

            // Garante que a aba ativa ainda exista na lista visível, se não, pula para primeira
            this.$nextTick(() => {
                const temAbaAtiva = this.visibleTabs.find(t => t.key === this.activeTabKey);
                if (!temAbaAtiva && this.visibleTabs.length > 0) {
                    this.activeTabKey = this.visibleTabs[0].key;
                }
            });

            this.userTour01();
        },
        removeFilter(filterType) {
            if (filterType === 'situacao') return; // Impede remoção do filtro padrão
            this.filters[filterType] = null;
            this.filterCards();
        },
        async loadProgress() {
            try {
                const params = new URLSearchParams({
                    ambiente: this.filters.ambiente || "",
                });

                const res = await window.ErrosRede.buscarComRetry(`/api/v1/progresso/?${params.toString()}`);
                const data = await res.json();

                if (data.progresso && data.progresso.length > 0) {
                    this.updateProgressInCards(data.progresso);
                } else {
                    this.updateProgressInCards([]);
                }
            } catch (error) {
                const falha = reportJsError("Error fetching progress:", error);
                // Só encerra o indicador de carregamento; não apaga progresso já exibido.
                this.finalizarCarregamentoProgresso();
                if (falha.causa !== 'navegando' && falha.causa !== 'aba_oculta') {
                    const texto = `Não foi possível carregar o progresso. ${falha.mensagem}`;
                    window.ErrosRede.mostrarAviso(window.ErrosRede.comCodigo(texto, falha.eventId), {
                        aoTentarNovamente: () => this.loadProgress(),
                    });
                }
            }
        },
        finalizarCarregamentoProgresso() {
            Object.values(this.salasPorCategoria).forEach(cards => {
                cards.forEach(card => {
                    card.progress_loading = false;
                });
            });
        },
        updateProgressInCards(progressData) {
            const progressMap = {};
            progressData.forEach(p => {
                const key = `${p.ambiente_id}_${p.id}`;
                progressMap[key] = p;
            });

            Object.keys(this.salasPorCategoria).forEach(category => {
                this.salasPorCategoria[category].forEach(card => {
                    const key = `${card.ambiente_id}_${card.id}`;
                    if (progressMap[key]) {
                        card.hasprogress = progressMap[key].hasprogress;
                        card.progress = progressMap[key].progress;
                    } else {
                        card.hasprogress = false;
                        card.progress = null;
                    }
                    card.progress_loading = false;
                });
            });
        },
        resetFilters() {
            this.filters = {
                situacao: 'inprogress',
                semestre: null,
                periodo: null,
                modulo: null,
                disciplina: null,
                curso: null,
                ambiente: null
            };
            this.saveFilters();
            this.filterCards();
        },
        saveFilters() {
            localStorage.setItem('filters', JSON.stringify(this.filters));
        },
        loadFilters() {
            const savedFilters = localStorage.getItem('filters');
            if (savedFilters) {
                try {
                    const parsedFilters = JSON.parse(savedFilters);
                    this.filters = {
                        ...this.filters, // Valores padrão
                        ...parsedFilters // Sobrescreve com os salvos
                    };
                } catch (e) {
                    reportJsError('Erro ao carregar filtros:', e);
                }
            }
        },
        changeShortnameStyle(shortname) {
            shortname = shortname.trim();
            const regexShortname = /^(\d+\.\d+\.\d+\.\w+)\.(\w+\.\d+)(#\d+)?$/;
            const match = shortname.match(regexShortname);

            if (match) {
                const grupo1 = match[1];
                const grupo2 = match[2];
                const grupo3 = match[3] || '';
                return `${grupo1} ${grupo2} ${grupo3}`.trim();
            } else {
                return shortname;
            }
        },
        canToggleVisible(card) {
            axios
                .get("/api/v1/set_visible/", {
                    params: {
                        ava: card.ambiente.titulo,
                        courseid: card.id,
                        visible: card.visible,
                    },
                })
                .then(() => {
                    return true;
                })
                .catch((error) => {
                    return false;
                });
        },
        toggleVisible(card) {
            const action = card.visible ? "ocultar" : "publicar";

            this.showConfirmation(action, (confirmed) => {
                if (confirmed) {
                    const new_status = card.visible ? '0' : '1';
                    axios
                        .get("/api/v1/set_visible/", {
                            params: {
                                ava: card.environment,
                                courseid: card.id,
                                visible: new_status,
                            },
                        })
                        .then((response) => {
                            card.visible = new_status == 1;
                        })
                        .catch((error) => {
                            console.debug(error);
                        });
                }
            });
        },
        toggleFavourite(item) {
            const new_status = item.isfavourite ? 0 : 1;
            const params = new URLSearchParams({
                ava: item.environment,
                courseid: item.id,
                favourite: new_status,
            });

            fetch(`/api/v1/set_favourite/?${params.toString()}`)
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }
                    return response.json();
                })
                .then(data => {
                    item.isfavourite = new_status === 1;
                })
                .catch(error => {
                    reportJsError('Erro ao atualizar favorito:', error);
                });
        },
        togglePreference(category, key, value) {
            const params = new URLSearchParams({
                category: category,
                key: key,
                value: value
            });

            fetch(`/api/v1/set_user_preference/?${params.toString()}`)
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`Erro HTTP! status: ${response.status}`);
                    }
                    return response.json();
                })
                .then(data => {
                    if (data.error) {
                        console.error("Erro ao atualizar preferência:", data.error.message);
                        return;
                    }

                    // Atualiza a UI conforme a preferência
                    if (key === "zoom_level") {
                        document.body.setAttribute("data-zoom", value);
                        return;
                    }

                    if (key === "color_mode") {
                        const modes = this.preferences.color_mode_options;

                        // remove todos
                        modes.forEach(m => {
                            document.body.classList.remove(`color_mode_${m}`);
                        });

                        // adiciona o selecionado
                        document.body.classList.add(`color_mode_${value}`);
                        return;
                    }

                    document.body.classList.toggle(key, value === true || value === "true");
                })
                .catch(error => {
                    reportJsError("Erro na requisição:", error);
                });
        },

        async enrollCourse(item) {
            // Previne duplo clique se já estiver carregando
            if (this.loading) return;

            this.loading = true;

            const idAmbiente = item.ambiente_id;
            const idCurso = item.id;
            console.log(item.ambiente_url);

            const url = `/curso/${idAmbiente}/${idCurso}/enrol/`;

            try {
                const response = await axios.post(url, {}, {
                    headers: { 'X-CSRFToken': this.getCsrfToken() }
                });

                if (response.data.status === 'enrolled' || response.data.status === 'reactivated') {
                    item.is_enrolled = true;
                    this.filterCards(false);

                    // Opcional: Se quiser forçar o redirecionamento, descomente a linha abaixo
                    // window.location.href = `/course/view.php?id=${idCurso}`;
                } else {
                    console.error('Erro na inscrição:', response.data);
                    alert("Não foi possível realizar a inscrição. Tente novamente.");
                }
            } catch (error) {
                const falha = reportJsError('Erro:', error);
                const message = error.response?.data?.message || falha?.mensagem || "Erro de comunicação com o servidor.";
                alert(window.ErrosRede?.comCodigo(message, falha.eventId) ?? message);
            } finally {
                this.loading = false;
            }
        },
        async enrollFromDetails(idAmbiente, idCurso, moodleUrl) {

            this.loading = true;
            const url = `/curso/${idAmbiente}/${idCurso}/enrol/`;

            try {
                const response = await axios.post(url, {}, {
                    headers: { 'X-CSRFToken': this.getCsrfToken() }
                });

                console.log('Resposta da inscrição:', response.data);

                if (response.data.status === 'enrolled' || response.data.status === 'reactivated') {
                    // Após inscrição, redireciona para o curso no Moodle
                    window.location.href = `${moodleUrl}/course/view.php?id=${idCurso}`;
                } else {
                    console.error('Erro na inscrição:', response.data);
                }
            } catch (error) {
                const falha = reportJsError('Erro:', error);
                const message = error.response?.data?.message || falha?.mensagem || "Erro de comunicação com o servidor.";
                alert(window.ErrosRede?.comCodigo(message, falha.eventId) ?? message);
            } finally {
                this.loading = false;
            }
        },
        unenrollCourse(item) {
            // Chamamos o showConfirmation passando a ação 'cancelar',
            // o callback assíncrono e o nome do curso como contexto extra.
            this.showConfirmation('cancelar', async (confirmed) => {
                if (!confirmed) return;

                if (this.loading) return;
                this.loading = true;

                const idAmbiente = item.ambiente_id;
                const idCurso = item.id;

                const url = `/curso/${idAmbiente}/${idCurso}/unenrol/`;

                try {
                    const response = await axios.post(url, {}, {
                        headers: { 'X-CSRFToken': this.getCsrfToken() }
                    });

                    console.log('Resposta do cancelamento:', response.data);

                    if (response.data.status === 'unenrolled' || response.status === 200) {
                        item.is_enrolled = false;
                        this.filterCards(false);
                    } else {
                        console.error('Erro no cancelamento:', response.data);
                        alert("Não foi possível cancelar a inscrição.");
                    }
                } catch (error) {
                    const falha = reportJsError('Erro:', error);
                    const message = error.response?.data?.message || falha?.mensagem || "Erro de comunicação com o servidor ao cancelar a matrícula.";
                    alert(window.ErrosRede?.comCodigo(message, falha.eventId) ?? message);
                } finally {
                    this.loading = false;
                }
            }, item.fullname);
        },

        cycleAccessibility() {
            const currentIndex = this.preferences.zoom_options.indexOf(this.preferences.zoom_level);
            const nextIndex = (currentIndex + 1) % this.preferences.zoom_options.length;
            this.preferences.zoom_level = this.preferences.zoom_options[nextIndex];
            this.togglePreference('accessibility', 'zoom_level', this.preferences.zoom_level);
        },
        cycleColorMode() {
            const modes = this.preferences.color_mode_options;
            const current = this.preferences.color_mode;

            const currentIndex = modes.indexOf(current);
            const nextIndex = (currentIndex + 1) % modes.length;

            const next = modes[nextIndex];
            this.preferences.color_mode = next;

            // Salva no Moodle / backend
            this.togglePreference('accessibility', 'color_mode', next);
        },
        colorModeLabel(mode) {
            switch (mode) {
                case 'default': return 'Padrão';
                case 'high_contrast': return 'Alto contraste';
                case 'low_contrast': return 'Contraste reduzido';
                case 'colorblind': return 'Amigável a daltônicos';
                case 'grayscale': return 'Escala de cinza';
                default: return mode;
            }
        },
        goToCourse(item) {
            window.location.href = item.url;
        },
        goToCourseUrl(item) {
            return item.url;
        },
        mostrarGauge(e) {
            const overlay = document.createElement('div');
            overlay.className = 'loading-overlay';

            const spinner = document.createElement('div');
            spinner.className = 'loading-spinner';

            const text = document.createElement('div');
            text.className = 'loading-text';
            text.textContent = 'Carregando, aguarde...';

            // insere dentro do overlay
            overlay.appendChild(spinner);
            overlay.appendChild(text);

            // adiciona overlay ao body
            document.body.appendChild(overlay);
        },
        clearGauge() {
            window.addEventListener("pageshow", (event) => {
                if (event.persisted) {
                    const overlay = document.querySelector('.loading-overlay');
                    if (overlay) overlay.remove();
                }
            })
        },
        showConfirmation(action, callback, itemName = '') {
            const modal = document.getElementById("popup-modal");
            const title = document.getElementById("popup-modal-message-title");
            const message = document.getElementById("popup-modal-message");
            const confirmBtn = document.getElementById("modal-confirm");
            const cancelBtn = document.getElementById("modal-cancel");
            const modalContent = modal.querySelector(".popup-modal-content");

            // Tratamento específico para o unenrollCourse
            if (action === 'cancelar') {
                title.innerHTML = `Tem certeza que deseja cancelar sua inscrição em:<br><strong>${itemName}</strong>?`;
                message.innerHTML = `Ao cancelar, você perderá o acesso a este curso.`;
                confirmBtn.innerText = "Sair do curso";
                cancelBtn.innerText = "Voltar";
            } else {
                // Lógica original para ocultar/publicar diários
                title.innerHTML = `Gostaria de <strong>${action}</strong> esse diário?`;
                confirmBtn.innerText = action;
                cancelBtn.innerText = "Cancelar";

                if (action == 'publicar') {
                    message.innerHTML = `Ao publicar este diário os alunos terão acesso ao conteúdo`;
                }
                if (action == 'ocultar') {
                    message.innerHTML = `Ao ocultar este diário os alunos <strong>não</strong> terão acesso ao conteúdo`;
                }
            }

            modal.classList.remove("hidden");

            const closeModal = (confirmed) => {
                modal.classList.add("hidden");
                confirmBtn.removeEventListener("click", confirmHandler);
                cancelBtn.removeEventListener("click", cancelHandler);
                modal.removeEventListener("click", outsideClickHandler);
                callback(confirmed);
            };

            const confirmHandler = () => closeModal(true);
            const cancelHandler = () => closeModal(false);

            // Fecha ao clicar fora do conteúdo do modal
            const outsideClickHandler = (event) => {
                if (!modalContent.contains(event.target)) {
                    closeModal(false);
                }
            };

            confirmBtn.addEventListener("click", confirmHandler);
            cancelBtn.addEventListener("click", cancelHandler);
            modal.addEventListener("click", outsideClickHandler);
        },

        async userTour01() {
            let completou_tour = false;
            try {
                const response = await fetch('get_tour_status/');
                const data = await response.json();
                completou_tour = data.completed_tour;
            } catch (error) {
                reportJsError('Erro:', error);
            }

            if (completou_tour != true) {

                const dicaPadrao = "<p style='text-align: center'><b>Você SEMPRE pode clicar na área destacada para testar.</b></p>";
                const steps = [
                    {
                        element: ".topbar",
                        title: "Aqui estão suas salas",
                        content: "<p>Você pode acessar seus diários, salas de coordenação, salas de práticas e reutilizáveis.</p><p>Clique em cada aba para ver a lista de salas.</p>" + dicaPadrao,
                        placement: "bottom-start",
                        onPrevious: () => {
                            try {
                                fetch('set_tour_completed/')
                                    .then(response => response.json())
                                    .then(data => console.log(data))
                                    .catch(error => reportJsError('Erro:', error));
                            } catch (e) {
                                reportJsError('Erro fechar o tour:', e);
                            }
                        },
                    },
                    {
                        element: "#btn-toggle-sidebar",
                        title: "Gaveta de menus",
                        content: '<p>Seus menus estão todos de gaveta que você pode abrir e fechar o quanto quiser.</p><p>Clique em <button id="btn-toggle-sidebar-usertour" onclick="document.getElementById(\'btn-toggle-sidebar\').click();" style="background-color: var(--verde-escuro);color: #fff;border-radius: 5px;padding: 0 5px;">&lt;&gt;</button> para alternar.</p>',
                        placement: "bottom-start",
                        onNext: () => {
                            try {
                                const elemento = document.getElementById('btn-toggle-filter');
                                if (elemento && !elemento.classList.contains('active')) {
                                    elemento.click();
                                }
                            } catch (e) {
                                reportJsError('Erro ao clicar no elemento:', e);
                            }
                        }
                    },
                    {
                        element: "#btn-toggle-filter",
                        title: "Filtros",
                        content: "<p>Não localizou a sala? Experimente alterar os filtros.</p>",
                        placement: "bottom-start",
                        onPrevious: () => {
                            try {
                                const elemento = document.getElementById('btn-toggle-filter');
                                if (elemento && !elemento.classList.contains('active')) {
                                    elemento.click();
                                }
                            } catch (e) {
                                reportJsError('Erro ao clicar no elemento:', e);
                            }
                        },
                        onNext: () => {
                            try {
                                const elemento = document.getElementById('btn-toggle-accessibility');
                                if (elemento && !elemento.classList.contains('active')) {
                                    elemento.click();
                                }
                            } catch (e) {
                                reportJsError('Erro ao clicar no elemento:', e);
                            }
                        },
                    },
                    {
                        element: "#btn-toggle-accessibility",
                        title: "Acessibilidade",
                        content: "<p>Aqui você pode deixar a fonte mais acessível para disléxicos.</p><p>Continuamos trabalhando para adicionar recursos de acessibilidade.</p>",
                        placement: "top-start",
                        onPrevious: () => {
                            try {
                                const elemento = document.getElementById('btn-toggle-filter');
                                if (elemento && !elemento.classList.contains('active')) {
                                    elemento.click();
                                }
                            } catch (e) {
                                reportJsError('Erro ao clicar no elemento:', e);
                            }
                        },

                        onNext: () => {
                            try {
                                const elemento = document.getElementById('btn-toggle-help');
                                if (elemento && !elemento.classList.contains('active')) {
                                    elemento.click();
                                }
                            } catch (e) {
                                reportJsError('Erro ao clicar no elemento:', e);
                            }
                        }
                    },
                    {
                        element: "#btn-toggle-help",
                        title: "Ainda precisa de ajuda?",
                        content: "<ul>" +
                            "<li>Acesse nossa <b>Central de Ajuda</b> para tirar dúvidas das mais diversas.</li>" +
                            "<li>Tenha seus direitos protegidos pela <b>Ouvidoria</b> do IFRN.</li>" +
                            "<li>Use nossa lista de <b>contatos</b> caso precise entrar em contato por telefone.</li>" +
                            "<li>Necessita de um atendimento para uma demanda? Use uma das nossas <b>Centrais de Atendimento</b> no SUAP.</li>" +
                            "</ul>",
                        placement: "top-start",
                        onPrevious: () => {
                            try {
                                const elemento = document.getElementById('btn-toggle-accessibility');
                                if (elemento && !elemento.classList.contains('active')) {
                                    elemento.click();
                                }
                            } catch (e) {
                                reportJsError('Erro ao clicar no elemento:', e);
                            }
                        },
                        onNext: () => {
                            try {
                                const elemento = document.getElementById('btn-toggle-profile');
                                if (elemento && !elemento.classList.contains('active')) {
                                    elemento.click();
                                }
                            } catch (e) {
                                reportJsError('Erro ao clicar no elemento:', e);
                            }
                        }
                    },
                    {
                        element: "#btn-toggle-profile",
                        title: "Menu do usuário",
                        content: "<p>Links rápidos, trocar para o tema anterior, alterar preferências e sair. Está tudo aqui, pensado em você!</p>",
                        placement: "top-start",
                        onPrevious: () => {
                            try {
                                const elemento = document.getElementById('btn-toggle-help');
                                if (elemento && !elemento.classList.contains('active')) {
                                    elemento.click();
                                }
                            } catch (e) {
                                reportJsError('Erro ao clicar no elemento:', e);
                            }
                        },
                        onNext: () => {

                            try {
                                fetch('set_tour_completed/')
                                    .then(response => response.json())
                                    .then(data => console.log(data))
                                    .catch(error => reportJsError('Erro:', error));
                                const elemento = document.getElementById('btn-toggle-profile');
                                if (elemento && elemento.classList.contains('active')) {
                                    elemento.click();
                                }
                            } catch (e) {
                                reportJsError('Erro ao clicar no elemento:', e);
                            }
                        },
                    },
                ];
                if (this.diarios && this.diarios.length > 0) {
                    steps.splice(1, 0, {
                        element: ".text-decoration-none",
                        title: "Sua sala de aula",
                        content: "<p>Você pode acessar suas salas clicando no <b>nome da sala ou no identificador</b> da sala.</p>" +
                            "<p>Aprenda nos próximos passos como usar os filtros para encontrar salas específicas, passadas, planejadas ou favoritas.</p>",
                        placement: "bottom-start",
                    });
                    steps.splice(2, 0, {
                        element: ".painel-card-details-info-unfavourite, .painel-card-details-info-favourite",
                        title: "Favorite uma sala",
                        content: "<p>Você tem muitas salas? Favorite as que você vai estudar mais neste semestre, então acesse elas <b>filtrando pelas favoritas<b>.",
                        placement: "bottom-end",
                    });
                }
                try {
                    const wt = new WebTour();
                    wt.setSteps(steps);
                    wt.start();
                } catch (e) {
                    reportJsError('Erro ao adicionar passos do tour:', e);
                }
            }
        }
    }
});


app.mount('#app');
