# Backlog 02 — Axiom Flow reaches the application

> Pending work. Index in [README.md](README.md).

## What this backlog is

What sets Axiom apart from a list manager is **Axiom Flow**: the system picks
the next action, one at a time, and learns from what the person does. Its
domain **already exists and is the most polished part of the core** — but no
use case uses it, so none of it reaches an interface.

What is in place today (2026-09-24):

| Piece | Where | Status |
| --- | --- | --- |
| `FlowEngine.get_next_action(candidates, state, profile, now)` → `FlowDecision` | `b_domain/engines/flow_engine.py` | ready; hierarchy session → ultradian break → friction → empty backlog → ranking |
| `UserFlowState` (energy, session, focus, momentum, streak, skips) | `b_domain/value_objects/flow_state.py` | ready; immutable, `record_*` methods return a copy |
| `UserBehaviorProfile` / `UserBehaviorMetrics` + repositories | `b_domain/value_objects/`, `b_domain/ports/repositories/` | ready; enterprise persists them |
| `UserBehaviorMetricsAggregator`, `UserBehaviorLearner` | `b_domain/services/` | ready; `UpdateUserBehaviorHandler` only reacts to `TaskCompletedEvent` |
| `TaskLanguageEngine` | `b_domain/engines/task_language_engine.py` | ready; pt/en |
| Events `TaskStarted`, `TaskAbandoned`, `FlowMomentumBroken`, `RewardEarned` | `b_domain/events/` | defined; **none is emitted** |
| Interactive simulator | `d_fake_infra/__main__.py` (local, gitignored) | orchestrates all of this in memory — the best reference for how the pieces fit |

The vision (Flow, Hook Model, Fogg, momentum, microtasks, focus mode) is in
`diretrizes.md`, local and outside git. This file lists only the technical
work.

## Before starting: the product decision

**Decided by the owner on 2026-09-24: Flow stays off for now.** The engine
was left off on purpose: to make sense, the system needs to know energy,
available time, duration and complexity of the tasks — and asking for that
all the time is exactly the friction Axiom promises to remove. No part of
this backlog starts before there is an answer to "how does Flow work with
the least explicit data collection". Hints the code already has: natural
language inference (Part 4), behavior learning (Part 5), heuristic cold start
(Part 6).

## Breakdown

| Part | Scope | Branch | Depends on |
| --- | --- | --- | --- |
| **1** | Execution lifecycle: start, pause, skip, abandon | `feat/backlog02-part1-execution-lifecycle` | Backlog 01 |
| **2** | Flow session and persisted state | `feat/backlog02-part2-flow-session` | 1 |
| **3** | "What's next?" — `GetNextActionUseCase` | `feat/backlog02-part3-next-action` | 2 |
| **4** | Natural language creation | `feat/backlog02-part4-natural-creation` | Backlog 01 P1 |
| **5** | Learning wired to every event | `feat/backlog02-part5-learning` | 1, 2 |
| **6** | Flow Engine v2 (due dates, aging, cold start, microtasks) | `feat/backlog02-part6-flow-v2` | 3 |

---

## Part 1 — Execution lifecycle

- [ ] Entity methods still missing: `start` (→ `IN_PROGRESS`, emits
  `TaskStartedEvent`), `pause`, `skip` (records `last_skipped_at`), `abandon`
  (emits `TaskAbandonedEvent`), `defer`. The state machine already allows
  these transitions.
- [ ] Use cases `StartTask` (opens a `TimeEntry`), `PauseTask`, `SkipTask`,
  `AbandonTask` (close the `TimeEntry`). `CompleteTaskUseCase` already closes
  timers — today nobody opens them.
- [ ] `ReopenTask`, `ArchiveTask`, `CancelTask` (the entity methods exist).

## Part 2 — Flow session and persisted state

- [ ] `FlowStateRepository` (port) + attribute on the `UnitOfWork`.
- [ ] `StartFlowSession` (reported energy, session duration/end, context) and
  `EndFlowSession`; `FlowSessionStarted/Ended` events (new).
- [ ] Update `UserFlowState` from the Part 1 events (`record_completion`,
  `record_skip`, `record_abandon`, `record_rest`), emitting
  `FlowMomentumBrokenEvent` when the streak breaks.

## Part 3 — `GetNextActionUseCase`

- [ ] Build the candidates: the user's pending/reopened tasks, **without the
  blocked ones** (the engine does not filter blocking — only the skip
  cooldown), in the active context.
- [ ] Call the `FlowEngine` with state and profile; return a DTO that
  represents each `FlowDecisionType` (task, break, intervention, empty
  backlog, end of session).
- [ ] Decide whether the suggestion marks the task as `SUGGESTED`.
- [ ] **Determinism:** the engine uses `random.uniform` for the exploration
  noise. Inject the randomness source (or a seed) so tests are reproducible.
- [ ] Engine tests per pillar (today the engine has almost no unit tests).

## Part 4 — Natural language creation

- [ ] `SmartCreateTaskUseCase`: free text → `TaskLanguageEngine.infer` →
  `CreateTaskInputDTO` → the normal creation flow. The configuration
  (lexicons, archetypes) arrives by injection, not by reading a file in the
  core (see Backlog 01, Part 1).
- [ ] The context map comes from the user's real contexts (today it is a
  hard-coded `{"work": "ctx_1"}`).
- [ ] Also return the inference confidence, so the interface can decide
  whether to ask for confirmation.

## Part 5 — Learning wired to every event

- [ ] `UpdateUserBehaviorHandler` also reacts to skip, abandon, pause and rest
  (the aggregator already has `record_task_skipped`, `record_task_abandoned`,
  `record_pause`, `record_rest`, `record_focus_*`).
- [ ] Per-task telemetry: `attempt_count`, `success_count`,
  `average_duration_minutes` really updated (today they stay at 0 — and the
  recurrence handler depends on the last one).
- [ ] `RewardModel` + `RewardEarnedEvent`: decide whether they go in now or
  wait for an interface that shows them.

## Part 6 — Flow Engine v2

Promises from the March `todo.md` that do not exist yet:

- [ ] Due date weight / exponential urgency ("Pain Score") and a lateness
  penalty.
- [ ] Aging (an old task slowly rises).
- [ ] Explicit cold start (no history: priority → duration → low
  complexity).
- [ ] Microtasks: automatic classification (≤ 5 min) and a fallback when
  momentum is low or there is inactivity.
- [ ] Score from the task's success history.
- [ ] Tags on the `Task` entity (the parser already recognizes `#tag`; the
  entity does not store them) and a cycle detector for `depends_on`.
