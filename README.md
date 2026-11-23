# Painel AVA

> **_APENAS PARA DESENVOLVIMENTO_** no IFRN, **USE apenas neste sentido**.

O **Painel AVA** é um dashboard com todos os cursos e inscrições que dos AVA que com os quais ele integra, desta
forma cada usuário tem acesso aos cursos/diários em que está inscrito sem precisar procurar em vários Moodles.

O **Painel AVA** é parte da **[SUAP/AVA Suite](https://suap-ava-suite.github.io/index.html)**, veja lá como o que é
como desenvolver, implantar ou usar a Suite.

> _**Este projeto não integra o SUAP ao Moodle. Se tua necessidade é essa, procure
> o `integrador-ava`.**_

Encontrou um problema no **Painel AVA**, aba uma
[issue](https://github.com/suap-ava-suite/djangoapp-painel_ava/issues),
ou melhor, faça um fork e abra uma pull request.

Encontrou um problema no **SUAP/AVA Suite**]**, aba uma
[issue](https://github.com/suap-ava-suite/suap-ava-suite.github.io/issues),
ou melhor, faça um fork e abra uma pull request.

## Fale conosco

1. Sobre **código ou documentação**, usar o Github tem mais chances de sucesso do que usar o email
   corporativo de desenvolvedor, ou e-Mail corporativo do setor do desenvovedor.
2. Se for para **fechamento de parceria**, é melhor procurar a [Diretoria de Educação a Distância e Tecnologias
Educacionais (DEAD)](mailto:dead.zl@ifrn.du.br) do IFRN.

## Screenshots da versão corrente

### Desktop

![screenshot](docs/images/screenshot.v5.web.png)

### Mobile

![screenshot](docs/images/screenshot.v5.mobile.png)

Confira a [evolução do design](docs/evolucao-do-design.md).

## Monitoramento HTTP

O Django expõe métricas de entrada e das chamadas ao Moodle/SUAP em `/metrics`, protegido
por `PAINEL_METRICS_TOKEN`. A configuração de coleta com Prometheus e ServiceMonitor está descrita em
[monitoramento](docs/monitoramento.rst).
