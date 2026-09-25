# Backlog 02 — O Axiom Flow chega à aplicação

> Trabalho pendente. Índice em [README.md](README.md).

## O que este backlog é

O que diferencia o Axiom de um gerenciador de listas é o **Axiom Flow**: o
sistema escolhe a próxima ação, uma por vez, e aprende com o que a pessoa faz.
O domínio disso **já existe e é a parte mais trabalhada do core** — mas nenhum
use case o usa, e por isso nada dele chega a uma interface.

O que está no lugar hoje (24/09/2026):

| Peça | Onde | Situação |
| --- | --- | --- |
| `FlowEngine.get_next_action(candidatas, estado, perfil, now)` → `FlowDecision` | `b_domain/engines/flow_engine.py` | pronto; hierarquia sessão → pausa ultradiana → fricção → backlog vazio → ranking |
| `UserFlowState` (energia, sessão, foco, momentum, streak, skips) | `b_domain/value_objects/flow_state.py` | pronto; imutável, métodos `record_*` devolvem cópia |
| `UserBehaviorProfile` / `UserBehaviorMetrics` + repositórios | `b_domain/value_objects/`, `b_domain/ports/repositories/` | prontos; enterprise persiste |
| `UserBehaviorMetricsAggregator`, `UserBehaviorLearner` | `b_domain/services/` | prontos; `UpdateUserBehaviorHandler` só reage a `TaskCompletedEvent` |
| `TaskLanguageEngine` | `b_domain/engines/task_language_engine.py` | pronto; pt/en |
| Eventos `TaskStarted`, `TaskAbandoned`, `FlowMomentumBroken`, `RewardEarned` | `b_domain/events/` | definidos; **nenhum é emitido** |
| Simulador interativo | `d_fake_infra/__main__.py` (local, gitignored) | orquestra tudo isso em memória — é a melhor referência de como as peças se encaixam |

A visão (Flow, Hook Model, Fogg, momentum, microtasks, focus mode) está em
`diretrizes.md`, local e fora do git. Este arquivo lista só o trabalho técnico.

## Antes de começar: a decisão de produto

**Decidido em 24/09/2026 pelo dono: o Flow fica desligado por enquanto.** O
motor não foi ligado de propósito: para ele fazer sentido, o sistema precisa
saber energia, tempo disponível, duração e complexidade das tarefas — e pedir
isso o tempo todo é exatamente a fricção que o Axiom promete eliminar. Nenhuma
parte deste backlog começa antes de haver uma resposta para "como o Flow
funciona com o mínimo de coleta explícita". Pistas que o código já tem:
inferência por linguagem natural (Parte 4), aprendizado por comportamento
(Parte 5), cold start por heurística (Parte 6).

## Divisão

| Parte | Recorte | Branch | Depende de |
| --- | --- | --- | --- |
| **1** | Ciclo de vida da execução: iniciar, pausar, pular, abandonar | `feat/backlog02-parte1-ciclo-de-execucao` | Backlog 01 |
| **2** | Sessão de fluxo e estado persistido | `feat/backlog02-parte2-sessao-de-fluxo` | 1 |
| **3** | "Qual a próxima?" — `GetNextActionUseCase` | `feat/backlog02-parte3-proxima-acao` | 2 |
| **4** | Criação por linguagem natural | `feat/backlog02-parte4-criacao-natural` | Backlog 01 P1 |
| **5** | Aprendizado ligado a todos os eventos | `feat/backlog02-parte5-aprendizado` | 1, 2 |
| **6** | Flow Engine v2 (prazos, envelhecimento, cold start, microtasks) | `feat/backlog02-parte6-flow-v2` | 3 |

---

## Parte 1 — Ciclo de vida da execução

- [ ] Métodos de entidade que ainda faltam: `start` (→ `IN_PROGRESS`, emite
  `TaskStartedEvent`), `pause`, `skip` (grava `last_skipped_at`), `abandon`
  (emite `TaskAbandonedEvent`), `defer`. A máquina de estados já permite essas
  transições.
- [ ] Use cases `StartTask` (abre um `TimeEntry`), `PauseTask`, `SkipTask`,
  `AbandonTask` (fecham o `TimeEntry`). O `CompleteTaskUseCase` já fecha
  timers — hoje ninguém os abre.
- [ ] `ReopenTask`, `ArchiveTask`, `CancelTask` (métodos de entidade existem).

## Parte 2 — Sessão de fluxo e estado persistido

- [ ] `FlowStateRepository` (porta) + atributo no `UnitOfWork`.
- [ ] `StartFlowSession` (energia informada, duração/fim da sessão, contexto)
  e `EndFlowSession`; eventos `FlowSessionStarted/Ended` (novos).
- [ ] Atualizar o `UserFlowState` a partir dos eventos da Parte 1
  (`record_completion`, `record_skip`, `record_abandon`, `record_rest`),
  emitindo `FlowMomentumBrokenEvent` quando o streak quebra.

## Parte 3 — `GetNextActionUseCase`

- [ ] Montar as candidatas: pendentes/reabertas do usuário, **sem as
  bloqueadas** (o motor não filtra bloqueio — só cooldown de skip), no
  contexto ativo.
- [ ] Chamar o `FlowEngine` com estado e perfil; devolver um DTO que
  represente cada `FlowDecisionType` (tarefa, pausa, intervenção, backlog
  vazio, fim de sessão).
- [ ] Decidir se a sugestão marca a tarefa como `SUGGESTED`.
- [ ] **Determinismo:** o motor usa `random.uniform` para o ruído de
  exploração. Injetar a fonte de aleatoriedade (ou uma semente) para os testes
  serem reprodutíveis.
- [ ] Testes do motor por pilar (hoje o motor quase não tem teste unitário).

## Parte 4 — Criação por linguagem natural

- [ ] `SmartCreateTaskUseCase`: texto livre → `TaskLanguageEngine.infer` →
  `CreateTaskInputDTO` → fluxo normal de criação. A configuração (léxicos,
  arquétipos) chega por injeção, não por leitura de arquivo no core (ver
  Backlog 01, Parte 1).
- [ ] O mapa de contextos vem dos contextos reais do usuário (hoje é
  `{"work": "ctx_1"}` fixo).
- [ ] Devolver também a confiança da inferência, para a interface decidir se
  pede confirmação.

## Parte 5 — Aprendizado ligado a todos os eventos

- [ ] `UpdateUserBehaviorHandler` reagir também a skip, abandono, pausa e
  descanso (o agregador já tem `record_task_skipped`, `record_task_abandoned`,
  `record_pause`, `record_rest`, `record_focus_*`).
- [ ] Telemetria por tarefa: `attempt_count`, `success_count`,
  `average_duration_minutes` atualizados de verdade (hoje ficam em 0 — e o
  handler de recorrência depende do último).
- [ ] `RewardModel` + `RewardEarnedEvent`: decidir se entram agora ou ficam
  para uma interface que os mostre.

## Parte 6 — Flow Engine v2

Promessas do `todo.md` de março que ainda não existem:

- [ ] Peso de prazo / urgência exponencial ("Pain Score") e penalidade de
  atraso.
- [ ] Envelhecimento (tarefa antiga sobe aos poucos).
- [ ] Cold start explícito (sem histórico: prioridade → duração → baixa
  complexidade).
- [ ] Microtasks: classificação automática (≤ 5 min) e fallback quando o
  momentum está baixo ou há inatividade.
- [ ] Score por histórico de sucesso da tarefa.
- [ ] Tags na entidade `Task` (o parser já reconhece `#tag`; a entidade não
  guarda) e detector de ciclo em `depends_on`.
