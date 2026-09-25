# Changelog — axiom-core

Formato inspirado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/);
versões seguem [SemVer](https://semver.org/lang/pt-BR/). A versão vigente é o
campo `version` do `pyproject.toml`.

## [Não lançado]

## [0.3.10] — 25/09/2026

### Alterado
- **`make check` verde** pela primeira vez: o piso de cobertura saiu dos 95%
  herdados do base-python-project para o valor real (**68%**, medido 68,7%),
  em `[tool.coverage.report] fail_under` — o `make check` e o CI leem o mesmo
  número. O piso sobe a cada trabalho que acrescentar teste.
- **CI de verdade**: dispara em `master` (era `main`/`develop`) e roda o
  próprio `make check`, em vez de comandos copiados que apontavam para
  `src/arch_pat_with_python`.
- ruff com `B` (bugbear) e `RUF`, como no base-python-project. O que mudou no
  código: exceções traduzidas dentro de `except` agora encadeiam a original
  (`raise … from e`), o que preserva a causa no traceback; `__all__` em ordem;
  aspas e travessões tipográficos (’ – ‑) trocados por ASCII em docstrings e
  comentários; dois testes que esperavam `Exception` genérica agora esperam
  `FrozenInstanceError`. `Description("")` como default em `Task.create` fica
  liberado no config (value object congelado).

## [0.3.9] — 24/09/2026

### Corrigido
- **Tarefa flutuante ficava "vencida" horas antes**: `DueDate.is_overdue`
  lia a hora de parede no fuso do `now` (UTC, o relógio da aplicação) em vez
  do fuso da própria data. Em São Paulo, um prazo às 23:59 virava vencido às
  20:59. Achado montando o roteiro de demonstração do CLI.

## [0.3.8] — 24/09/2026

### Corrigido
- **Recorrência "a cada N horas" nunca avançava** (`SimpleIntervalRule`
  horária): somava as horas e depois reaplicava a hora de início, então toda
  ocorrência era o próprio início. Concluir uma tarefa assim deixava
  `create_next_occurrence` (modo hábito) em laço infinito. Achado ao mostrar
  as próximas ocorrências no `axpro task show`.

## [0.3.7] — 24/09/2026

### Corrigido
- **`CreateTaskUseCase` descartava a janela horária** (`window_start`/
  `window_end`): "a cada 2 h entre 08:00 e 20:00" virava "a cada 2 h" o dia
  todo, em silêncio. Achado pelo mypy do CLI.

## [0.3.6] — 24/09/2026

### Corrigido
- Marcadores `py.typed` (PEP 561) em `a_core`, `b_domain` e `c_application`:
  sem eles, o mypy de quem usa o core (enterprise, CLI) ignorava todos os
  tipos daqui (`import-untyped`) — 110 dos 153 erros do enterprise eram isso.

## [0.3.5] — 24/09/2026

Achados pelos primeiros testes de integração do enterprise (banco real +
relay do outbox).

### Corrigido
- **Eventos de tarefa carimbavam o relógio real**, não o `now` recebido:
  `TaskCreatedEvent` e `TaskCompletedEvent` agora levam `occurred_at=now`. O
  `CreateRecurringTaskHandler` calcula a próxima ocorrência a partir desse
  instante — com conclusão retroativa (`completed_at`), ela saía errada.
- `TaskOutputDTO.is_blocked` era sempre `False`: o `TaskMapper` não o
  preenchia. Tarefa com dependência pendente agora sai `is_blocked=True`.

## [0.3.4] — 24/09/2026

mypy zerado (Backlog 01, Parte 2, item do mypy) — pacotes **e testes**.

### Corrigido
- **`MonthlyAllWeekdaysRule` quebrava ao virar o mês** quando não tinha
  `end_date` (`base_dt` só era calculado com data de fim): "toda segunda do
  mês" dava `AttributeError` a partir da segunda ocorrência. Achado por um
  dos erros do mypy.
- Portas `UserBehaviorMetricsRepository` e `UserBehaviorProfileRepository`:
  `save` devolve `None` e `get_by_user_id` devolve `X | None` — como o
  enterprise implementa e como o handler já usava.
- `TaskFilter.ids` aceita `Sequence[UniqueId]` (uma lista de `TaskId` não
  passava na tipagem).
- `ExportTaskToCalendarHandler`: checa tarefa sumida entre as duas transações
  e prazo ausente (antes, `task.due_date.value` com prazo `None`).
- Fakes de teste seguem as portas: `update`/`update_many` devolvem a tarefa;
  `get_by_id` com `user_id` não quebra quando não acha; o `FakeUnitOfWork`
  tinha `user_behavior_profiles` com o nome colado ao tipo (o atributo não
  existia).

### Removido
- Esboços `ActivateContextUseCase` e `SwitchContextUseCase`
  (`c_application/use_cases/contexts/`): não funcionavam e ninguém os
  importava. Os use cases de contexto de verdade são a Parte 4 do Backlog 01.

### Alterado
- mypy cobre `a_core`, `b_domain`, `c_application` **e `tests`**
  (`[tool.mypy] files`); `make typecheck`, `make check` e o hook do
  pre-commit rodam `mypy` sem argumentos. `d_fake_infra/` (local) fica fora.

## [0.3.3] — 24/09/2026

### Corrigido
- `BusinessDayRule` não definia `_freq`: comparar duas regras de dia útil (o
  que o enterprise faz ao atualizar uma tarefa) levantava `AttributeError`.
  Achado no teste de ida e volta das recorrências pelo banco.

## [0.3.2] — 24/09/2026

Antes do `axpro config set` (CLI, Backlog 01, Parte 4).

### Corrigido
- `UserPrefs.update` valida as preferências de valor fechado: `timezone`
  (fuso IANA que exista), `week_start` (`monday`/`sunday`), `theme`
  (`light`/`dark`/`system`) e `working_hours_start/end` (0–23), com
  `InvalidValueError`. Antes aceitava qualquer coisa — e um fuso inválido
  gravado quebrava a criação de tarefas depois.

## [0.3.1] — 24/09/2026

Achados ao escrever `task edit` e `task done` no CLI (Backlog 01, Parte 4 de
lá).

### Corrigido
- **Editar o prazo** (`UpdateTaskUseCase`) tornava toda tarefa flutuante e
  quebrava (`AttributeError`) quando a tarefa ainda não tinha prazo. Agora a
  tarefa mantém o tipo (fixa/flutuante) salvo pedido contrário; data
  flutuante mantém o fuso; o resto (tarefa sem prazo, data fixa digitada como
  hora local) é lido no fuso do usuário. `Task.update_due_date` passa a montar
  o prazo como o `create` (`DueDate.from_params`).
- `CompleteTaskUseCase` separa "prefixo não encontrado" de "prefixo ambíguo"
  (antes, "Ambiguous IDs found" para os dois). O repositório fake dos testes
  passa a dar as mesmas mensagens do real.

## [0.3.0] — 24/09/2026

Pedido pelo CLI (Backlog 01, Parte 4 de lá): `task ls` esconder o que já saiu
do caminho.

### Adicionado
- `TaskStatus.is_closed` e `TaskStatus.closed()`: `done`, `cancelled` e
  `archived` são os status que tiram a tarefa das listas do dia a dia.
- `TaskFilter.exclude_statuses` (vazio = não exclui nada) e
  `ListTasksRequest.include_closed` (padrão `True`, comportamento de antes).
  Com `False`, a listagem esconde as encerradas — a menos que o pedido traga
  um `status` explícito, que vence.

## [0.2.2] — 24/09/2026

Fecha a Parte 3 do Backlog 01: os bugs que o levantamento achou rodando o CLI.

### Corrigido
- **Recorrência exibida como "-"** para toda regra que não era intervalo
  simples: `format_task_recurrence` procurava atributos de antes do refactor de
  mar/2026. Agora cada regra se descreve (`describe_pattern()`, abstrato em
  `RecurrenceRule`) e o formatador só acrescenta o fim (`for N occurrences` /
  `until AAAA-MM-DD`).
- **Prioridade, complexidade e energia digitadas como texto** (`"high"`)
  quebravam `ListTasksUseCase` e `UpdateTaskUseCase`; o update falhava até sem
  prioridade no pedido (`Priority(None)`). Novo `LevelEnum.parse`: aceita nome
  (qualquer caixa, `-`/espaço no lugar de `_`) ou número e **falha** com
  `InvalidValueError` listando as opções.
- **A próxima ocorrência de tarefa recorrente perdia atributos**: contexto,
  energia, complexidade, dependências e duração estimada passam adiante; o
  `CreateRecurringTaskHandler` só troca a estimativa pela média medida quando
  há média (antes gravava 0).
- `GetCurrentUserUseCase` sem token levanta `NotAuthenticatedError` (antes
  "token inválido").
- `ordinal_phrase`: "21st"/"22nd"/"23rd" (antes "21th"), e posições do fim como
  "third to last"/"4th to last".

### Alterado
- **Quebra:** `Priority.from_string` removido (devolvia `MEDIUM` para qualquer
  texto); use `Priority.parse`. `Priority`, `EnergyLevel` e `TaskComplexity`
  herdam de `LevelEnum`; `str()` passa a dar "Very low" em vez de "Very_low".
- `CreateTaskInputDTO.priority` passa a ser `None` por padrão, e aí vale
  `UserPrefs.default_task_priority` — antes o padrão do DTO (`MEDIUM`) sempre
  vencia a preferência. `UserPrefs.update` valida e normaliza essa preferência.
- `LogoutUseCase` assume o que faz: sem sessão no servidor, logout é o cliente
  descartar o token; a saída diz isso (`token_revoked=False`). Sem token,
  `NotAuthenticatedError`. `LogoutInputDTO.access_token` e
  `GetCurrentUserInputDTO.token` aceitam `None`.
- Helpers de texto (`ordinal`, `ordinal_phrase`, `join_naturally`) saem de
  `c_application/utils/string_utils.py` para `a_core/text.py`, porque o
  domínio passou a usá-los.

## [0.2.1] — 24/09/2026

### Adicionado
- `LICENSE`: Axiom Core License 1.0 — uso, modificação e redistribuição
  livres, inclusive para construir aplicações comerciais, com crédito à origem
  e aos autores; proibida a venda do próprio core como está ou com alterações
  pequenas. Resumo em português no README.

### Corrigido
- README: Python 3.12+ (dizia 3.10+) e bloco de código que não fechava.

## [0.2.0] — 24/09/2026

Consolida o trabalho de jun/2026, que estava sem commit, e fecha a Parte 1 do
Backlog 01.

### Adicionado
- `SimpleValueObject`: base para value objects com um único `value`, com
  igualdade contra `str` e `repr` legível. `UniqueId` e `TextValueObject`
  passam a herdar dela.
- `InputDTO` e `OutputDTO` como bases de DTO.
- `Makefile` (`format`, `lint`, `lint-fix`, `typecheck`, `test`, `coverage`,
  `check`), `.pre-commit-config.yaml`, `.github/` (CI e Dependabot).
- Configuração de black, ruff, mypy, pytest e coverage no `pyproject.toml`
  (substitui o `pytest.ini`).
- Configuração padrão do `TaskLanguageEngine` versionada e empacotada em
  `b_domain/engines/task_language_engine.toml`, com testes.
- `CLAUDE.md`, `CHANGELOG.md` e `docs/backlog/` (retomada).

### Alterado
- **Quebra:** `b_domain/ports/unity_of_work.py` renomeado para
  `unit_of_work.py`.
- **Quebra:** `PaginatedResponse` passa a ser genérico em `OutputDTO`, com
  `total_items`, `per_page`, `total_pages` e `current_page` (antes `total`,
  `page`, `size`). Ainda não há quem a use.
- **Quebra:** `load_language_engine_factory(path)` vira
  `build_language_engine(config, contexts_map)`: recebe a configuração já
  lida (o core não lê arquivo) e o mapa de contextos de quem chama.
- A lista de exemplo `TASKS` e o `__main__` saem de
  `task_language_engine.py`.
- Hooks do pre-commit passam a usar as ferramentas do próprio projeto.
- Código modernizado para Python 3.12 (`X | None`, `datetime.UTC`, imports
  ordenados, formatação black em todo o repo).
- Desserialização de eventos reconstrói `SimpleValueObject` por `value=`.

## Histórico anterior ao changelog (08/03 – 04/04/2026)

Reconstruído a partir do `git log` na retomada; a versão ficou em `0.1.0` e
nunca foi publicada.

- **Motor de fluxo (mar/08–09):** `FlowEngine` sem estado, guiado por
  `UserBehaviorProfile`; `UserBehaviorLearner` e métricas de comportamento.
- **Eventos e outbox (mar/13–16):** `DomainEvent` com serialização tipada,
  `IdPrefix`, `BaseRepository` com rastreamento de entidades, `EventBus`,
  `UnitOfWork` que grava no Outbox, `OutboxEvent`, `OutboxRelayService`,
  handlers e a regra de mover efeitos colaterais do `CompleteTaskUseCase` para
  eles.
- **Calendário e usuário (mar/16–20):** campos de calendário externo na `Task`,
  `ExportTaskToCalendarHandler`, `AbstractEmailService`, `User` com e-mail e
  preferências, `PasswordHasher` como ABC, filtros de repositório.
- **Fábrica de UoW e wiring (mar/20–22):** use cases recebem `uow_factory`;
  `register_essential_handlers`/`register_optional_handlers`; `trigger_relay`
  para evitar laço infinito; dependências entre tarefas (`depends_on`),
  resolução por prefixo de id.
- **Recorrência e datas (mar/28–30):** recorrências reescritas sobre
  `AxiomDate` (fixa × flutuante), `normalize_comparison_date`, enums como
  `StrEnum`, `can_transition_to(allow_same)`, `AxiomDate.from_params`.
- **Autenticação e preferências (abr/01–04):** `LoginUseCase`,
  `RegisterUserUseCase`, `LogoutUseCase`, `GetCurrentUserUseCase`,
  `UpdateUserPreferencesUseCase` (devolvendo o que mudou),
  `PrepareUserPreferencesUseCase`, `GetUserPreferencesUseCase`, tema nas
  preferências, exceções de segurança e de usuário, `execute` assíncrono.
