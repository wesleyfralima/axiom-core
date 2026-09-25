# docs/backlog/done/ — histórico do que já foi finalizado

Este arquivo é **só o mapa**: explica a convenção da pasta e indexa o que já
fechou, para que uma sessão não precise abrir os arquivos grandes só para
descobrir onde um assunto mora.

## Regra de organização

- **Um arquivo por objetivo fechado**, que chega aqui inteiro, depois de 100%
  concluído em [../todo/](../todo/README.md).
- **Não se edita retroativamente**, exceto para corrigir erro de registro
  (data, link). O arquivo existe para não reabrir decisão já fechada.
- Todo arquivo abre com `# Nome ✅ (data)` e uma linha apontando para este
  índice.
- Cada linha da tabela é **uma frase**, o suficiente para decidir se vale abrir
  o arquivo. Ao fechar algo, acrescente a linha aqui no mesmo commit.

## Como procurar sem estourar contexto

1. Comece pela tabela abaixo.
2. Sem saber o arquivo: `grep -rn "termo" docs/backlog/done/`.
3. Dentro de um arquivo: `grep -n "^#\{1,2\} "` para as seções, `sed -n 'A,Bp'`
   para o trecho.

## Índice

| Arquivo | Período | Do que trata |
| --- | --- | --- |

Nada fechado ainda. O trabalho anterior à retomada (mar–jun/2026) está
resumido no [CHANGELOG.md](../../../CHANGELOG.md).
