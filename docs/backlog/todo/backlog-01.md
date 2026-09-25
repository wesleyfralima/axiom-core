# Backlog 01 — Retomada do axiom-core

> Trabalho pendente. Índice em [README.md](README.md).

## O que este backlog é

O core parou em 04/04/2026 (último commit) com uma rodada de modernização
feita em jun/2026 e nunca commitada. Este backlog não traz funcionalidade
nova: ele **devolve o repo a um estado confiável** — tudo commitado, `make
check` verde, os bugs do levantamento corrigidos — e o deixa apresentável como
vitrine. O Axiom Flow (funcionalidade nova) é o [Backlog 02](backlog-02.md).

O levantamento de 24/09/2026 encontrou:

1. **~110 arquivos de WIP**: 85 staged e 69 com mudanças não staged por cima
   dos staged. A maior parte é mecânica (ruff `UP`, black); o resto é
   refactor real (ver [CHANGELOG](../../../CHANGELOG.md), "Não lançado").
2. **185 testes passando**, black e ruff limpos, **mypy com 18 erros**,
   **cobertura 57%** — e o `make check` exige 95%.
3. **O rename `unity_of_work` → `unit_of_work` quebrou o enterprise**, e com
   ele o CLI. O enterprise é adaptado no Backlog 01 dele; aqui o que importa é
   commitar o rename junto com a nota de quebra.
4. Alguns erros do mypy são **bugs de runtime**, confirmados pelo CLI.

## Divisão

| Parte | Recorte | Branch | Depende de |
| --- | --- | --- | --- |
| **1** ✅ | Consolidar o WIP em commits temáticos | `chore/backlog01-parte1-consolidar-wip` | — |
| **2** | `make check` verde e CI de verdade | `chore/backlog01-parte2-check-verde` | 1 |
| **3** | Bugs encontrados no levantamento | `fix/backlog01-parte3-bugs-do-levantamento` | 1 |
| **4** | Contextos: da entidade ao use case | `feat/backlog01-parte4-contextos` | 1 |
| **5** | Vitrine: README, licença, badges | `docs/backlog01-parte5-vitrine` | 2 |

---

## Parte 1 — Consolidar o WIP ✅ (24/09/2026)

**No lugar hoje:** `git status` com `M`, `MM`, `R`, `D` e `??` misturados; o
staged foi feito em algum momento e o trabalho continuou por cima.

- [x] Revisar o WIP e separar em commits. *Resolvido em 24/09/2026:* separar
  por tema dentro de cada arquivo exigiria `git add -p` e deixaria commits
  intermediários quebrados (as mudanças atravessam camadas). Ficaram três
  commits: tooling (`ed813a1`), pre-commit alinhado ao projeto (`68076b2`) e o
  código inteiro modernizado (`64c7791`, 185 testes passando).
- [x] `task_lang_engine_conf.toml` versionado. *Resolvido em 24/09/2026*
  (`4d21039`): virou `b_domain/engines/task_language_engine.toml`, empacotado
  no wheel; `load_language_engine(path)` virou
  `build_language_engine(config, contexts_map)`, sem I/O no core.
- [x] `TASKS` e o `__main__` fora do módulo de domínio. *Resolvido em
  24/09/2026:* foram para `d_fake_infra/sample_tasks.py` (local), e o
  simulador lê o TOML ele mesmo.
- [x] `version` `0.2.0` e seção fechada no CHANGELOG. *Resolvido em
  24/09/2026.*
- Achado no caminho: os hooks do pre-commit fixavam versões antigas de black
  e ruff e discordavam do `make check`; e `poetry run` nos hooks pegava o venv
  errado quando outro estava ativo. *Resolvido em 24/09/2026 (`68076b2`):*
  hooks locais chamando `.venv/bin/…` — era um item da Parte 2.

## Parte 2 — `make check` verde e CI de verdade

**No lugar hoje:** o `ci.yml` foi copiado do base-python-project: dispara em
`main`/`develop` (o branch é `master`), roda `mypy src` e mede cobertura de
`src/arch_pat_with_python`. O `.pre-commit-config.yaml` fixa versões antigas
(ruff 0.11, black 25.1, mypy 1.15) diferentes das do `pyproject`.

- [ ] CI: branch `master`; `mypy a_core b_domain c_application`; cobertura
  sobre os três pacotes (o mesmo comando do `make check`).
- [x] Alinhar versões do pre-commit com as do `pyproject`. *Resolvido em
  24/09/2026, na Parte 1 (`68076b2`).*
- [ ] Zerar os 18 erros do mypy. Grupos:
  - `User | None` atribuído a `User` depois do `if not user` (create,
    get_prefs, update_prefs) — só tipagem;
  - `Priority(str)` / `TaskComplexity(str)` — **bug**, ver Parte 3;
  - `ListTasksRequest.ids` → `TaskFilter.ids` (`TaskId` × `UniqueId`);
  - `export_task_handler.py` (`str | None`, `DueDate | None`, `Task | None`);
  - `contexts/activate_context.py` — esboço quebrado, ver Parte 4.
- [ ] Cobertura: 57% hoje. Fixar o piso **no valor real** (ex.:
  `--cov-fail-under=57`) para o check ficar verde já, e subir o piso a cada
  parte que acrescentar teste. Os maiores buracos: engines, services de
  comportamento, handlers, use cases de auth/user.
- [ ] Testar `ruff` com o conjunto do base-python-project (`B`, `RUF`) e
  adotar se o custo for baixo.

## Parte 3 — Bugs encontrados no levantamento

Todos confirmados rodando o CLI contra o core atual (24/09/2026).

- [ ] **Recorrência exibida como "-"** para toda regra que não é
  `SimpleIntervalRule`. `format_task_recurrence`
  (`c_application/utils/task_utils.py`) procura `frequency`, `by_week_days`,
  `by_month_days`, `nth_business_day` — nomes de antes do refactor de
  28/03/2026; as regras atuais têm `days_of_week`, `days_of_month`, `nth_day`
  etc. Proposta: cada regra sabe se descrever (método polimórfico), e o
  formatador só monta a frase. Teste por tipo de regra.
- [ ] **`task ls --priority high` falha** ("Invalid priority: high"):
  `ListTasksUseCase` faz `Priority(dto.priority)` com texto. Mesmo erro em
  `TaskComplexity(dto.complexity)` e em `UpdateTaskUseCase`. Converter por nome.
  Atenção: `Priority.from_string` devolve `MEDIUM` para qualquer texto
  desconhecido — silencioso demais para entrada de usuário; deve falhar.
- [ ] **A próxima ocorrência de tarefa recorrente perde atributos.**
  `Task._recreate_task_with_date` chama `Task.create` só com título,
  descrição, prioridade, prazo, pai e recorrência: somem `context_id`,
  `required_energy_level`, `complexity`, `depends_on`. E o
  `CreateRecurringTaskHandler` sobrescreve `estimated_duration_minutes` com
  `average_duration_minutes`, que é **0** porque nada o calcula.
- [ ] `whoami` sem login responde "The provided token is invalid."
  (`GetCurrentUserUseCase` levanta `InvalidTokenError` para token ausente);
  token ausente deve ser `NotAuthenticatedError`.
- [ ] `LogoutUseCase` não invalida nada (TODO no código). Decidir: para o uso
  local, logout = apagar o token do cliente, e o use case diz isso; revogação
  de verdade só quando houver servidor (sync/web).

## Parte 4 — Contextos: da entidade ao use case

**No lugar hoje:** a entidade `Context` existe; `UserPrefs.active_context_id`
existe; `CreateTaskUseCase` já herda o contexto ativo. Mas **não há porta de
repositório** de contexto no `UnitOfWork`, `ActivateContextUseCase` usa
`self.current_user` e `uow.contexts` (que não existem) e
`SwitchContextUseCase` não faz nada. O enterprise já tem modelo ORM e mapper.

- [ ] `ContextRepository` em `b_domain/ports/repositories/` + atributo
  `contexts` no `UnitOfWork` + fake no `conftest`.
- [ ] Use cases: criar, listar, renomear/excluir contexto; trocar o contexto
  ativo (grava em `UserPrefs.active_context_id` e emite
  `ContextSwitchedEvent`, que já existe).
- [ ] `TaskOutputDTO.context_name/context_icon` preenchidos (hoje sempre
  `None`).
- [ ] Remover os dois esboços atuais.

## Parte 5 — Vitrine

**No lugar hoje:** o README fala em Python 3.10+ (o projeto exige 3.12), não
mostra como rodar os testes nem a arquitetura em camadas com as regras; **não
há `LICENSE`** (repo público sem licença = todos os direitos reservados).

- [x] Decidir a licença com o dono e adicionar `LICENSE`. *Resolvido em
  24/09/2026:* licença própria, **Axiom Core License 1.0** (base MIT +
  atribuição obrigatória de origem e autores + proibição de revender o core
  como está). Não é "open source" no sentido OSI, por causa da cláusula 3; é
  *source-available* permissiva.
- [ ] README: o que é o projeto, diagrama das camadas, as regras (zero
  dependências, tempo injetado, eventos via outbox), exemplos de uso de
  `AxiomDate` e de recorrência, como rodar `make check`.
- [ ] Badges de CI e cobertura.
- [ ] Revisar o que é público: `diretrizes.md`/`todo.md` continuam fora do
  git; nada de plano de negócio no README.
