# Changelog — axiom-core

Format inspired by [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [SemVer](https://semver.org/). The current version is the
`version` field of `pyproject.toml`.

## [Unreleased]

## [0.6.0] — 2026-09-25

Reopen, archive and cancel a task (Backlog 02, Part 1, last item). For a
recurring task, cancelling skips one occurrence and the series goes on,
unless the cancel ends the series (owner's decision, 2026-09-25).
Enterprise and the CLI pick it up in 0.5.0 and 0.9.0.

### Added
- Use cases `ReopenTaskUseCase`, `ArchiveTaskUseCase` (both take
  `TaskByUserRequest`) and `CancelTaskUseCase` (`CancelTaskInputDTO`, with
  `end_series`); they return the task's `TaskOutputDTO`. Cancelling stops
  the task's running timers.
- `TaskCancelledEvent(task_id, user_id, end_series)`, raised by
  `Task.mark_as_cancelled`. `CreateRecurringTaskHandler` reacts to it (the
  next occurrence, unless `end_series`) and so does
  `UnlockTaskDependenciesHandler` (a cancelled blocker will never be done,
  so it no longer holds its dependents back). Interfaces that rehydrate
  events from the outbox must add it to their registry.
- `NotRecurringTaskError`: `end_series` on a task that does not repeat.
- `c_application/utils/task_utils.find_task(uow, ref, user_id)`: one of the
  user's tasks by ID prefix (`EntityNotFound`, `AmbiguousIdentifierError`).

### Changed
- **Archiving is only for a closed task** (done or cancelled); open ones
  are done or cancelled first. `ARCHIVED` is no longer reachable from
  `SOMEDAY`, `PENDING`, `SKIPPED` or `ABANDONED`.
- **The full list hides archived tasks**: `include_closed=True` brings back
  done and cancelled ones; archived tasks only show when asked for with
  `status="archived"`.
- `Task.reopen` only accepts a done or cancelled task and turns a recurring
  occurrence into a one-off task (its series already moved on when it
  closed), so completing it again does not start a second copy of the
  series. `Task.archive` and `Task.mark_as_cancelled` explain what is wrong
  when the task is in the wrong state.
- `REOPENED` and `PAUSED` can go to `CANCELLED`.
- The fake `TaskRepository.find_by_id_prefix` in the tests is scoped by
  user, like the real one.
- Coverage floor 73% → 73.8% (367 tests).

## [0.5.0] — 2026-09-25

The active context can limit the task list (owner's decision: with a
context active, `task ls` shows only its tasks).

### Added
- `ListTasksRequest.use_active_context` (default `False`, the previous
  behavior): without a `context_id`, the list is limited to the user's
  active context, when there is one. An explicit `context_id` still wins.
- `TaskListOutputDTO.context`: the context the list was limited to
  (requested or active, with `is_active`), or `None` when it spans every
  context — so the interface can say which one it is showing.

## [0.4.0] — 2026-09-25

Closes Backlog 01, Part 4: contexts, from the entity to the use case.
Requires axiom-enterprise 0.4.0 (it implements the new port).

### Added
- **Context use cases** (`c_application/use_cases/context/`):
  `CreateContextUseCase`, `ListContextsUseCase`, `UpdateContextUseCase`
  (name, icon, description), `DeleteContextUseCase` and
  `SwitchContextUseCase` (the active context, or none). A context is found
  by **name** (ignoring case) or by **ID prefix** (`find_context`); names are
  unique per user, ignoring case (`ContextNameTakenError`).
- `ContextRepository` port (`add`, `update`, `delete`, `get_by_id`,
  `list_by_user`). Its `delete` must detach the context's tasks.
- `User.switch_context(now, context_id | None)`: writes
  `UserPrefs.active_context_id` and emits `ContextSwitchedEvent` when the
  active context really changes.
- `Context.create(now, …)` validates name (1–100 characters) and icon
  (1–20); `Context.update(now, …)` changes only what it is given;
  `Context.matches_name`.
- `TaskOutputDTO.context_id`; `context_name` and `context_icon` are filled
  in by every task use case (they were always `None`).

### Changed
- **Breaking:** `UnitOfWork` has a `contexts: ContextRepository` attribute —
  implementations must provide it.
- **Breaking:** `Context.id` is a `ContextId` (was a plain `UniqueId`), and
  `Context.create` takes `now` (time is injected, like everywhere else).
- **Breaking:** `ContextSwitchedEvent.new_context_id` accepts `None` (the
  filter turned off). The unused `SwitchContextRequest` DTO is gone.
- `CreateTaskInputDTO.context_id` and `ListTasksRequest.context_id` accept a
  context **name** or ID prefix, and fail with `EntityNotFound` when it does
  not exist — the CLI's `task add --context work` used to fail with "Invalid
  context ID." A new task inherits the active context only if it still
  exists.
- Coverage floor 68% → 73% (335 tests).

## [0.3.11] — 2026-09-25

### Changed
- **ruff replaces black as the formatter** (`ruff format`), in `make format`,
  `make check` and the pre-commit hooks; black left the dev dependencies.
  The reformatting touched 17 files, with no code change.
- **The whole repository is in English**: comments, docstrings, test data,
  `README`, `CLAUDE.md`, backlogs and this changelog (earlier entries
  translated). The only Portuguese left is language data for understanding
  user input (`pt` sections of `task_language_engine.toml` and the tests that
  exercise them).

### Fixed
- `.gitignore`: `.DS_Store (para macOS)` was read as a literal pattern, so
  `.DS_Store` was never ignored.

## [0.3.10] — 2026-09-25

### Changed
- **`make check` green** for the first time: the coverage floor went from the
  95% inherited from base-python-project to the real value (**68%**, measured
  68.7%), in `[tool.coverage.report] fail_under` — `make check` and the CI
  read the same number. The floor goes up with every piece of work that adds
  tests.
- **A real CI**: it triggers on `master` (was `main`/`develop`) and runs
  `make check` itself, instead of copied commands that pointed at
  `src/arch_pat_with_python`.
- ruff with `B` (bugbear) and `RUF`, as in base-python-project. What changed
  in the code: exceptions translated inside `except` now chain the original
  (`raise … from e`), which keeps the cause in the traceback; `__all__`
  sorted; typographic quotes and dashes (’ – ‑) replaced by ASCII in
  docstrings and comments; two tests that expected a generic `Exception` now
  expect `FrozenInstanceError`. `Description("")` as a default in
  `Task.create` is allowed in the config (a frozen value object).

## [0.3.9] — 2026-09-24

### Fixed
- **A floating task became "overdue" hours early**: `DueDate.is_overdue`
  read the wall-clock time in the timezone of `now` (UTC, the application
  clock) instead of the date's own timezone. In São Paulo, a 23:59 due date
  became overdue at 20:59. Found while building the CLI demo script.

## [0.3.8] — 2026-09-24

### Fixed
- **"Every N hours" recurrence never advanced** (hourly
  `SimpleIntervalRule`): it added the hours and then reapplied the start
  time, so every occurrence was the start itself. Completing such a task left
  `create_next_occurrence` (habit mode) in an infinite loop. Found while
  showing the next occurrences in `axpro task show`.

## [0.3.7] — 2026-09-24

### Fixed
- **`CreateTaskUseCase` dropped the time window** (`window_start`/
  `window_end`): "every 2 h between 08:00 and 20:00" became "every 2 h" all
  day long, silently. Found by the CLI's mypy.

## [0.3.6] — 2026-09-24

### Fixed
- `py.typed` markers (PEP 561) in `a_core`, `b_domain` and `c_application`:
  without them, the mypy of the core's users (enterprise, CLI) ignored every
  type from here (`import-untyped`) — 110 of enterprise's 153 errors were
  this.

## [0.3.5] — 2026-09-24

Found by enterprise's first integration tests (real database + outbox
relay).

### Fixed
- **Task events were stamped with the real clock**, not the `now` received:
  `TaskCreatedEvent` and `TaskCompletedEvent` now carry `occurred_at=now`.
  `CreateRecurringTaskHandler` computes the next occurrence from that instant
  — with a backdated completion (`completed_at`), it came out wrong.
- `TaskOutputDTO.is_blocked` was always `False`: `TaskMapper` did not fill it
  in. A task with a pending dependency now comes out `is_blocked=True`.

## [0.3.4] — 2026-09-24

mypy at zero (Backlog 01, Part 2, the mypy item) — packages **and tests**.

### Fixed
- **`MonthlyAllWeekdaysRule` broke when the month turned** when it had no
  `end_date` (`base_dt` was only computed with an end date): "every Monday of
  the month" raised `AttributeError` from the second occurrence on. Found by
  one of the mypy errors.
- Ports `UserBehaviorMetricsRepository` and `UserBehaviorProfileRepository`:
  `save` returns `None` and `get_by_user_id` returns `X | None` — as
  enterprise implements them and as the handler already used them.
- `TaskFilter.ids` accepts `Sequence[UniqueId]` (a list of `TaskId` did not
  type-check).
- `ExportTaskToCalendarHandler`: checks for a task that vanished between the
  two transactions and for a missing due date (before,
  `task.due_date.value` with a `None` due date).
- Test fakes follow the ports: `update`/`update_many` return the task;
  `get_by_id` with `user_id` does not break when nothing is found; the
  `FakeUnitOfWork` had `user_behavior_profiles` with the name glued to the
  type (the attribute did not exist).

### Removed
- The `ActivateContextUseCase` and `SwitchContextUseCase` sketches
  (`c_application/use_cases/contexts/`): they did not work and nobody
  imported them. The real context use cases are Backlog 01, Part 4.

### Changed
- mypy covers `a_core`, `b_domain`, `c_application` **and `tests`**
  (`[tool.mypy] files`); `make typecheck`, `make check` and the pre-commit
  hook run `mypy` with no arguments. `d_fake_infra/` (local) stays out.

## [0.3.3] — 2026-09-24

### Fixed
- `BusinessDayRule` did not define `_freq`: comparing two business-day rules
  (which enterprise does when updating a task) raised `AttributeError`. Found
  by the recurrence round-trip test through the database.

## [0.3.2] — 2026-09-24

Before `axpro config set` (CLI, Backlog 01, Part 4).

### Fixed
- `UserPrefs.update` validates the closed-value preferences: `timezone` (an
  IANA zone that exists), `week_start` (`monday`/`sunday`), `theme`
  (`light`/`dark`/`system`) and `working_hours_start/end` (0–23), with
  `InvalidValueError`. It used to accept anything — and a stored invalid
  timezone broke task creation later.

## [0.3.1] — 2026-09-24

Found while writing `task edit` and `task done` in the CLI (its Backlog 01,
Part 4).

### Fixed
- **Editing the due date** (`UpdateTaskUseCase`) made every task floating and
  broke (`AttributeError`) when the task had no due date yet. Now the task
  keeps its kind (fixed/floating) unless asked otherwise; a floating date
  keeps its timezone; the rest (a task without a due date, a fixed date typed
  as local time) is read in the user's timezone. `Task.update_due_date` now
  builds the due date like `create` does (`DueDate.from_params`).
- `CompleteTaskUseCase` tells "prefix not found" apart from "ambiguous
  prefix" (before, "Ambiguous IDs found" for both). The tests' fake
  repository now gives the same messages as the real one.

## [0.3.0] — 2026-09-24

Requested by the CLI (its Backlog 01, Part 4): `task ls` hiding what is
already out of the way.

### Added
- `TaskStatus.is_closed` and `TaskStatus.closed()`: `done`, `cancelled` and
  `archived` are the statuses that take a task out of the day-to-day lists.
- `TaskFilter.exclude_statuses` (empty = excludes nothing) and
  `ListTasksRequest.include_closed` (default `True`, the previous behavior).
  With `False`, the listing hides closed tasks — unless the request carries an
  explicit `status`, which wins.

## [0.2.2] — 2026-09-24

Closes Backlog 01, Part 3: the bugs the survey found by running the CLI.

### Fixed
- **Recurrence shown as "-"** for every rule that was not a simple interval:
  `format_task_recurrence` looked for attributes from before the March 2026
  refactor. Now each rule describes itself (`describe_pattern()`, abstract on
  `RecurrenceRule`) and the formatter only adds the end (`for N occurrences`
  / `until YYYY-MM-DD`).
- **Priority, complexity and energy typed as text** (`"high"`) broke
  `ListTasksUseCase` and `UpdateTaskUseCase`; the update failed even without a
  priority in the request (`Priority(None)`). New `LevelEnum.parse`: accepts a
  name (any case, `-`/space instead of `_`) or a number and **fails** with
  `InvalidValueError` listing the options.
- **The next occurrence of a recurring task lost attributes**: context,
  energy, complexity, dependencies and estimated duration carry over;
  `CreateRecurringTaskHandler` only swaps the estimate for the measured
  average when there is an average (it used to store 0).
- `GetCurrentUserUseCase` without a token raises `NotAuthenticatedError`
  (before, "invalid token").
- `ordinal_phrase`: "21st"/"22nd"/"23rd" (before "21th"), and positions from
  the end as "third to last"/"4th to last".

### Changed
- **Breaking:** `Priority.from_string` removed (it returned `MEDIUM` for any
  text); use `Priority.parse`. `Priority`, `EnergyLevel` and `TaskComplexity`
  inherit from `LevelEnum`; `str()` now gives "Very low" instead of
  "Very_low".
- `CreateTaskInputDTO.priority` is now `None` by default, and then
  `UserPrefs.default_task_priority` applies — before, the DTO default
  (`MEDIUM`) always beat the preference. `UserPrefs.update` validates and
  normalizes that preference.
- `LogoutUseCase` owns what it does: with no server session, logout is the
  client discarding the token; the output says so (`token_revoked=False`).
  Without a token, `NotAuthenticatedError`. `LogoutInputDTO.access_token` and
  `GetCurrentUserInputDTO.token` accept `None`.
- Text helpers (`ordinal`, `ordinal_phrase`, `join_naturally`) move from
  `c_application/utils/string_utils.py` to `a_core/text.py`, because the
  domain started using them.

## [0.2.1] — 2026-09-24

### Added
- `LICENSE`: Axiom Core License 1.0 — free use, modification and
  redistribution, including to build commercial applications, with credit to
  the origin and the authors; selling the core itself as-is or with minor
  changes is forbidden. Summary in the README.

### Fixed
- README: Python 3.12+ (it said 3.10+) and a code block that did not close.

## [0.2.0] — 2026-09-24

Consolidates the June 2026 work, which was uncommitted, and closes Backlog
01, Part 1.

### Added
- `SimpleValueObject`: base for value objects with a single `value`, with
  equality against `str` and a readable `repr`. `UniqueId` and
  `TextValueObject` now inherit from it.
- `InputDTO` and `OutputDTO` as DTO bases.
- `Makefile` (`format`, `lint`, `lint-fix`, `typecheck`, `test`, `coverage`,
  `check`), `.pre-commit-config.yaml`, `.github/` (CI and Dependabot).
- black, ruff, mypy, pytest and coverage configuration in `pyproject.toml`
  (replaces `pytest.ini`).
- Default `TaskLanguageEngine` configuration versioned and packaged in
  `b_domain/engines/task_language_engine.toml`, with tests.
- `CLAUDE.md`, `CHANGELOG.md` and `docs/backlog/` (restart).

### Changed
- **Breaking:** `b_domain/ports/unity_of_work.py` renamed to
  `unit_of_work.py`.
- **Breaking:** `PaginatedResponse` is now generic over `OutputDTO`, with
  `total_items`, `per_page`, `total_pages` and `current_page` (before
  `total`, `page`, `size`). Nobody uses it yet.
- **Breaking:** `load_language_engine_factory(path)` becomes
  `build_language_engine(config, contexts_map)`: it receives the
  already-read configuration (the core does not read files) and the caller's
  context map.
- The sample `TASKS` list and the `__main__` leave `task_language_engine.py`.
- Pre-commit hooks now use the project's own tools.
- Code modernized for Python 3.12 (`X | None`, `datetime.UTC`, sorted
  imports, black formatting across the repo).
- Event deserialization rebuilds `SimpleValueObject` through `value=`.

## History before the changelog (2026-03-08 – 2026-04-04)

Rebuilt from `git log` at the restart; the version stayed at `0.1.0` and was
never published.

- **Flow engine (Mar 08–09):** stateless `FlowEngine`, driven by
  `UserBehaviorProfile`; `UserBehaviorLearner` and behavior metrics.
- **Events and outbox (Mar 13–16):** `DomainEvent` with typed serialization,
  `IdPrefix`, `BaseRepository` with entity tracking, `EventBus`, a
  `UnitOfWork` that writes to the Outbox, `OutboxEvent`,
  `OutboxRelayService`, handlers and the rule of moving
  `CompleteTaskUseCase`'s side effects into them.
- **Calendar and user (Mar 16–20):** external calendar fields on `Task`,
  `ExportTaskToCalendarHandler`, `AbstractEmailService`, `User` with e-mail
  and preferences, `PasswordHasher` as an ABC, repository filters.
- **UoW factory and wiring (Mar 20–22):** use cases receive `uow_factory`;
  `register_essential_handlers`/`register_optional_handlers`;
  `trigger_relay` to avoid an infinite loop; dependencies between tasks
  (`depends_on`), resolution by id prefix.
- **Recurrence and dates (Mar 28–30):** recurrences rewritten on top of
  `AxiomDate` (fixed × floating), `normalize_comparison_date`, enums as
  `StrEnum`, `can_transition_to(allow_same)`, `AxiomDate.from_params`.
- **Authentication and preferences (Apr 01–04):** `LoginUseCase`,
  `RegisterUserUseCase`, `LogoutUseCase`, `GetCurrentUserUseCase`,
  `UpdateUserPreferencesUseCase` (returning what changed),
  `PrepareUserPreferencesUseCase`, `GetUserPreferencesUseCase`, theme in the
  preferences, security and user exceptions, async `execute`.
