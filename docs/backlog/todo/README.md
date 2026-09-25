# docs/backlog/todo/ — trabalho pendente

Este arquivo é **só o mapa**: explica a convenção da pasta e lista o que existe
aqui. Nenhum item de tarefa mora nele — cada frente de trabalho tem o próprio
arquivo, para que uma sessão abra só o que precisa.

## Regra de organização

- **Um arquivo por objetivo.** Backlog numerado é `backlog-NN.md`; qualquer
  outra frente (uma dívida técnica isolada, uma auditoria) ganha nome
  descritivo em kebab-case.
- **Todo arquivo abre com título e uma linha de contexto** apontando para este
  índice, porque qualquer um deles pode ser aberto sozinho.
- **Um arquivo só sai daqui 100% concluído**, inteiro, para
  [../done/](../done/), com "resolvido em …" em cada item que ainda não tinha.
  Enquanto houver item aberto, o arquivo fica aqui — inclusive com os `[x]` —
  para não perder o porquê de cada decisão nem quebrar referências cruzadas.
- **Não se quebra um arquivo grande em menores** para caber na convenção; o
  corte por objetivo vale para trabalho novo.
- Se uma alteração fechar item de OUTRO arquivo (ou de outro repo do
  ecossistema), feche-o lá também, com data e contexto.
- Ao fechar um arquivo, mova a linha dele deste índice para o de `done/` no
  mesmo commit.

Workflow (branch, commit, versão, changelog) mora só no
[CLAUDE.md](../../../CLAUDE.md) — não se repete aqui.

## Índice

| Arquivo | Do que trata |
| --- | --- |
| [backlog-01.md](backlog-01.md) | Retomada (aberto em 24/09/2026): consolidar o WIP, deixar `make check` verde, corrigir os bugs achados no levantamento e apresentar o repo como vitrine |
| [backlog-02.md](backlog-02.md) | Axiom Flow chega à aplicação: use cases que ligam FlowEngine, TaskLanguageEngine e o aprendizado ao resto do sistema |
