Monitoramento HTTP e integrações
================================

O Django expõe contadores e histogramas Prometheus em ``/metrics``. A coleta cobre as
respostas do painel e as chamadas HTTP que ele faz ao Moodle e ao SUAP, incluindo as
sessões privadas de ``django_suap_auth`` no login OAuth. O Grafana consulta o Prometheus.

Ativação e coleta
-----------------

Defina ``PAINEL_METRICS_TOKEN`` com um segredo exclusivo e configure o mesmo valor como
Bearer token no Prometheus. Sem essa variável, ``/metrics`` responde 404; um token
incorreto recebe 403. A coleta funciona sem sessão, acesso ao banco ou login no SUAP.
O token é um segredo compartilhado exclusivo da coleta, gerado pelo administrador. Ele
não é um token do Moodle, do SUAP, de login de usuário ou um JWT. Armazene-o em um Secret
Kubernetes ou gerenciador de segredos e forneça o mesmo valor ao Django e ao Prometheus.
O token não deve ser colocado em URLs, versionado ou reutilizado como token do Moodle.

O Ingress padrão do chart encaminha o prefixo ``/`` ao Django, incluindo ``/metrics``.
Assim, quando esse Ingress está publicado na Internet, a rota também pode ser alcançada
externamente: sem token configurado responde 404; com token configurado exige autorização
e responde 403 se o token estiver ausente ou incorreto. Quem possui o token correto pode
ler as métricas pela URL pública. O Service ser ``ClusterIP`` não impede esse acesso via
Ingress. O token autentica a coleta, mas não torna o endpoint privado na rede.

A aplicação mantém a porta HTTP atual: nas VMs, a porta 80 encaminha para a porta 8000
do contêiner. O endpoint é ``:80/metrics``, sem uma porta adicional de métricas. Para
restringir o acesso pela URL pública, configure uma regra específica no proxy; o chart
atual não implementa esse isolamento de rede.

Em produção, o Prometheus de ``manchester`` coleta diretamente as duas VMs:

* ``cambia``: ``10.22.1.27:80/metrics``;
* ``pune``: ``10.22.0.112:80/metrics``.

Use ``monitoring/prometheus.yml`` como exemplo para acrescentar o job ``painel-ava`` à
configuração existente em ``/var/dockers/monitoramento/prometheus.yml`` no manchester.
Não substitua o arquivo completo: preserve os jobs atuais. O Django não lê esse exemplo
e ele não inicia ou instala o Prometheus. Monte o arquivo de credenciais no contêiner do
Prometheus em ``/etc/prometheus/secrets/painel/token`` e forneça seu conteúdo também na
variável ``PAINEL_METRICS_TOKEN`` de cada contêiner Django. O arquivo contém somente o
valor do token, sem o prefixo ``Bearer``. A preparação e a ativação em produção são etapas
operacionais posteriores; estas mudanças não configuram os servidores automaticamente.

O mesmo Prometheus continua coletando ``:9100/metrics`` pelo job ``node_exporter``
para CPU, memória, disco e rede. Esse job é independente das métricas HTTP do Django na
porta 80 e deve ser preservado. Não é necessário um segundo coletor.

No Kubernetes, o chart permite fornecer o segredo ao Django, sem criar recursos de
coleta. Crie um Secret no namespace do painel e configure::

    metrics:
      tokenSecret:
        name: painel-metrics
        key: token

O Secret deve conter a chave ``token`` com o mesmo valor do Bearer token. Para coletar
nesse ambiente, configure a descoberta de cada réplica no coletor administrado pela
infraestrutura. O chart não fornece ServiceMonitor e não depende do Prometheus Operator.
Coletar somente um endereço com balanceamento entre réplicas produz contagens incompletas.
O coletor acrescenta os rótulos ``job``, ``instance`` e ``application=painel-ava``.

.. _monitoramento-pre-release:

Verificações obrigatórias antes da release
------------------------------------------

Antes de publicar a release destas mudanças, registre o resultado das verificações abaixo
para cada ambiente de destino. A existência do Grafana, por si só, não comprova que exista
um Prometheus coletando a aplicação. Esta é uma verificação operacional obrigatória;
o pipeline atual não a executa automaticamente e os testes locais não a substituem.

1. Identificar o Prometheus que receberá as métricas e confirmar que está operacional.
   Registrar o responsável, o ambiente e a configuração de coleta. Em produção, a coleta
   será feita pelo Prometheus existente no manchester, sem dependência de Operator/CRDs.
2. Confirmar a criação do segredo de coleta e a configuração correspondente no Django e
   no coletor. Conferir o arquivo de credenciais montado e sua permissão de leitura pelo
   processo do Prometheus. Não registrar o valor do token nas evidências.
3. Validar a configuração completa com ``promtool check config`` antes de ativá-la.
   Validar a conectividade entre o coletor e cada réplica da aplicação na porta atual.
   Conferir os targets no Prometheus: cada réplica esperada deve aparecer com ``up=1``,
   sem erros de autorização. Preservar os jobs existentes e evitar coleta duplicada.
4. Em homologação, gerar tráfego nos endpoints do Django e nas integrações Moodle/SUAP;
   confirmar crescimento dos contadores e presença de amostras nos histogramas, incluindo
   chamadas com falha. Repetir a coleta com mais de um worker e conferir todas as réplicas.
5. Registrar o resultado da verificação de exposição de ``/metrics`` pela URL pública e a
   configuração de acesso adotada para a release. O chart atual permite alcançar essa
   rota pelo Ingress e exige o token para leitura; não comprova isolamento de rede.

Uma pendência na infraestrutura de coleta deve ser resolvida ou registrada como uma
implantação sem monitoramento ativado. Não anunciar a coleta como operacional antes de
validar os targets e as métricas em homologação.

Workers e ciclo de vida
-----------------------

A imagem de produção inicia pelo script ``gunicorn-entrypoint.sh``. Ele cria um diretório
multiprocess exclusivo e vazio antes de iniciar as migrações e o Gunicorn, definindo
``PROMETHEUS_MULTIPROC_DIR`` antes da importação do cliente Python. Todos os workers do
mesmo master compartilham esse diretório. ``child_exit`` informa a saída de workers ao
cliente Prometheus. O scrape agrega os processos da réplica; o Prometheus agrega réplicas.
O contador de processos finalizados é preservado até o reinício do master.

Se iniciar Gunicorn por outro comando, configure um diretório exclusivo e vazio por
master antes do processo Python, ou use o script fornecido. Nunca compartilhe esse
diretório entre réplicas. Na execução com um processo, sem a variável, o endpoint usa o
registro local. O diretório temporário fica no filesystem do contêiner e não requer volume
persistente; reinícios do contêiner/master iniciam novos contadores.

Métricas e interpretação
------------------------

* ``painel_http_server_requests_total{route,method,status}``: respostas do Django,
  incluindo 3xx e rejeições antecipadas dos middlewares.
* ``painel_http_server_request_duration_seconds{route,method}``: histograma do tempo
  até a criação da resposta Django, incluindo seus middlewares. Não mede o carregamento
  do navegador, entrega de streaming ou erros produzidos exclusivamente pelo proxy.
* ``painel_http_client_requests_total{dependency,environment,operation,purpose,method,status,result}``:
  chamadas externas, incluindo cada nova tentativa explícita do painel.
* ``painel_http_client_request_duration_seconds{dependency,environment,operation,purpose,method}``:
  duração das chamadas externas, incluindo falhas. Com ``requests`` sem streaming, inclui
  a leitura da resposta; redirecionamentos automáticos integram a duração da chamada.
* ``painel_http_client_invalid_json_total{dependency,environment,operation,purpose}``:
  respostas recebidas cujo JSON não pôde ser interpretado.
* ``painel_moodle_operations_total{environment,operation,outcome}``: resultado final
  da operação Moodle após as tentativas: ``success``, ``expected_absence``, ``failure``
  ou ``invalid_response``. Abrange também as consultas administrativas de diagnóstico.
* ``painel_moodle_batches_total{operation,outcome}``: consultas agregadas de salas e
  progresso. Os resultados são ``complete``, ``partial``, ``failure`` e ``no_targets``.

``dependency`` diferencia ``moodle`` de ``suap``. ``environment`` identifica o nome
cadastrado do Moodle; para o SUAP vale ``suap``. ``operation`` usa uma lista de serviços
Moodle e caminhos SUAP conhecidos/configurados; caminhos desconhecidos viram ``other``.
As rotas Django usam o padrão do resolvedor, preservando parâmetros como ``<int:id>``;
URLs sem rota são agrupadas em ``unmatched``. Métodos desconhecidos viram ``OTHER``.
URLs completas, query strings, usuários, senhas e tokens não aparecem nos rótulos.

``purpose=application`` identifica o tráfego das operações do painel; ``probe`` identifica
a consulta ao SUAP feita por ``/probes/readiness/``. Arquivos em ``/static/`` e ``/media/``,
``/metrics``, ``/health/`` e ``/probes/`` não entram nos indicadores HTTP de entrada.

``result=response`` preserva o status HTTP real, inclusive erros 4xx e 5xx. Sem resposta
HTTP, ``status=none`` e ``result`` distingue ``timeout``, ``connection_error``, ``tls_error``
e ``request_error``. Não se atribui um 5xx fictício a falhas de transporte. Há uma observação
por ``requests.Session.request``: redirects automáticos usam o status final e não geram
contagens individuais. A coleta não inclui chamadas efetuadas fora desse transporte.

A instrumentação de ``requests`` é instalada uma vez em ``AppConfig.ready``. Ela alcança
os brokers v1/v2 e as sessões da biblioteca OAuth. Consultas ao Moodle são identificadas
por um contexto explícito em cada worker, sem consultar o banco nessas threads. Chamadas
a terceiros fora dos destinos monitorados não geram séries. A coleta preserva exceções,
headers e comportamento de transporte da aplicação.

Um 404 com a mensagem de usuário ausente no Moodle é ``expected_absence`` e não torna
uma consulta agregada parcial. Uma resposta válida e vazia também pode ser completa.
Uma falha em parte dos ambientes produz ``partial``, mesmo que a API Django responda
200 com os demais dados. Falhas de comunicação, JSON inválido e erros ao combinar os
dados marcam o ambiente como falho. ``no_targets`` significa que não havia ambientes
selecionados. Não some contagens de entrada às de saída: são etapas diferentes.

A prontidão retorna 503 quando banco, cache ou SUAP falham e 200 quando todos funcionam,
independentemente de ``DEBUG``. Os retornos de erro de banco no middleware retornam 500.

Consultas no Grafana
--------------------

Configure uma fonte de dados Prometheus no Grafana para consultar as métricas descritas
acima. Os indicadores de entrada, Moodle e SUAP devem ficar separados. Use os rótulos de
rota, ambiente, operação e tipo de chamada para filtrar ou agrupar os dados. Não há arquivo
de dashboard fornecido neste repositório.

As séries nascem na primeira ocorrência. A ausência de uma série pode indicar que aquela
classe de status ainda não ocorreu ou que a coleta não está funcionando; confira ``up`` e
a saúde dos targets no Prometheus antes de interpretar ausência de dados como zero erros.

Os totais usam ``increase`` no período selecionado e são estimativas que consideram resets.
As taxas usam ``rate`` e expressam requisições por segundo; multiplique por 60 para uma taxa
por minuto. Para contar ocorrências em uma janela de um minuto, use ``increase(...[1m])``,
com intervalo de coleta que forneça amostras suficientes.

Os percentis usam ``histogram_quantile`` com os buckets somados antes do cálculo, permitindo
agregar corretamente os workers e as réplicas. Não se calcula a média dos percentis.
Os buckets vão de 5 ms a 60 s e incluem o bucket infinito. Durações acima de 60 s são
registradas, mas a estimativa dos percentis nessa faixa exige ajustar os buckets.
