# Changelog — axiom-core

Format inspired by [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [SemVer](https://semver.org/). The current version is the
`version` field of `pyproject.toml`.

## [Unreleased]

## [0.17.0] — 2026-09-26

Choosing the holiday region (Part 6 of the product backlog). Enterprise
0.13.0 and CLI 0.19.0 pick it up.

### Added
- **`ListHolidayRegionsUseCase`**: every country, a country's subdivisions
  (the query is its code: `BR`), or a search by code or name (`bra`,
  `Brasil`, `br-paulo`) — case and accents never matter, and when nothing
  contains the text, a name a typo away from it or from its start (`bras`;
  one letter up to five, two beyond) is found. Names are the provider's
  (English for countries). Marks the user's region.
- `HolidayRegion` (code and name); `HolidayProvider.regions(country)`.
- `c_application/utils/holiday_regions.find_regions`.
- **`UnknownHolidayRegionError`**: an unknown region — or one that is not
  even shaped like a code, such as "Brazil" — now says which ones are
  close ("Did you mean BR (Brazil)?").

### Changed
- Coverage floor 82.3% → 82.6% (565 tests).

## [0.16.0] — 2026-09-26

Business days (Part 6 of the product backlog): what a business day is now
belongs to the user. Enterprise 0.12.0 and CLI 0.18.0 pick it up.

### Added
- **`WorkCalendar`** (`b_domain/value_objects/work_calendar.py`): work
  days of the week, a region's holidays, and the user's own days, each
  above the one before. `CalendarDay` (a day off or a working day, **once
  or every year**; a one-off wins over a yearly one on the same date) and
  `CalendarDayKind`.
- **Preferences `work_days`** (`mon,tue,wed,thu,fri` by default; names or
  ranges such as `sun-thu`, stored in canonical form) and
  **`holiday_region`** (`BR`, `BR-SP`, `US-CA`…; empty: no holidays).
  `UserPrefs.work_weekdays`.
- **Ports**: `HolidayProvider` (a region's holidays, whether it is known,
  the country of a time zone) and `CalendarDayRepository`; the unit of work
  exposes `calendar_days` and `holidays`.
- **Use cases** `ShowWorkCalendarUseCase` (work days, region, and the
  holidays and own days from today up to a year ahead, or `ahead`; with no
  region, the one the time zone suggests), `SetCalendarDayUseCase` (adds or
  replaces; says when it changes nothing) and `RemoveCalendarDayUseCase`.
- `PrepareUserPreferencesUseCase` suggests a holiday region from the time
  zone (`timezone` in, `suggested_holiday_region` out); updating the
  preferences refuses a region whose holidays are not known.
- **Dates as `MM-DD`**: the next one, today included (`12-25`, `02-29` on
  the next leap year), with an optional `HH:MM` — in every date the user
  types.
- `RecurrenceRule.uses_business_days` / `with_business_days`,
  `Task.use_business_days` and `c_application/utils/work_calendar.py`
  (`load_work_calendar`, `use_work_calendar`: loaded only when a task
  needs it).

### Changed
- **"The Nth business day" counts the user's business days** — work days,
  their region's holidays, their own days — on create, edit, list, show,
  the next occurrence and the calendar export. It was Monday to Friday,
  hard-coded in three places (`# TODO: holidays`).
- `BusinessDayRule.is_business_day` defaults to Monday to Friday (it is
  the user's calendar, not data: nothing rebuilds it on the way back from
  storage any more); `RecurrenceFactory` no longer requires it.
- Coverage floor 80.2% → 82.3% (553 tests).

### Removed
- **The `skip_weekends` preference**, which nothing read: `work_days`
  replaces it (enterprise converts what is stored).

## [0.15.0] — 2026-09-26

Timers and estimates (Part 4 of the product backlog). Enterprise 0.11.0
and CLI 0.17.0 pick it up.

### Added
- **`StartTaskUseCase` / `PauseTaskUseCase`** (`TaskTimerOutputDTO`): a
  `TimeEntry` opens and closes; **one thing at a time** — starting a task
  pauses the one that was running (its pause is `caused_by` the start, so
  undoing the start resumes it). `Task.start` (→ in progress; a blocked or
  closed task cannot start) and `Task.pause`; `TaskPausedEvent`;
  `TaskStartedEvent` no longer needs a context or Flow's momentum.
  History actions `started` and `paused`.
- **Undo of timers**: undoing a start throws its session away; undoing a
  pause runs the same session again. Any other undo brings "in progress"
  back as paused (undo never starts a timer).
- **Estimates**: `estimated_minutes` on create (default: the
  `default_task_duration_minutes` preference, which did nothing) and edit
  (`Task.update_estimate`); in the snapshot and the edit history.
- **Estimates that learn**: a completion with measured time updates the
  task's running average (`Task.record_duration`), which becomes the next
  occurrence's estimate — the handler already used it; nothing computed it.
- `TaskOutputDTO.estimated_minutes`, `time_spent_minutes`, `running_since`
  (on show and on the timers' answers); `timer.time_of`.
- **Report**: time measured inside the period (the part of each session in
  it), in all and by context; estimated vs. actual of what was done with
  measured time, in all and by context; the best hours (when completions
  happen most, from 5 on).
- `Entity.peek_events()`; `TimeEntry.resume()`; `TimeEntryRepository.delete`.

### Fixed
- **A completion counted only the running session** (`actual_minutes`):
  every session of the task counts now, the paused ones too.

### Changed
- Coverage floor 79.2% → 80.2% (494 tests).

## [0.14.0] — 2026-09-26

Reports and series (Part 3 of the product backlog). Enterprise 0.10.0
stores the series; the CLI 0.16.0 has `axpro report` and `task log --series`.

### Added
- **`ReportUseCase`** (`ReportRequest`: the last 7 days by default, `week`
  from the user's `week_start`, `month`, or `start`/`end` as typed) →
  `ReportOutputDTO`: done, created, cancelled; done on time, late or
  without a due date — **against the due date the task had when it was
  completed** (its history snapshot); per day, by context and by priority;
  the series with something done or missed in the period (done, missed,
  current streak, completion rate), and how many others are going with
  nothing in it. An undone change does not count.
- **Series**: `Task.series_id` — set when a task gets a rule (the first
  occurrence's ID), carried to each next occurrence, kept in the snapshot
  (undo) and when the task stops repeating.
- `GetTaskHistoryUseCase` takes a `TaskHistoryRequest` (was
  `TaskByUserRequest`) with `series`: the whole series' history;
  `TaskHistoryOutputDTO.series_size`; each entry says its `task_id`.
- History port: `between(user, start, end)` and `list_for_tasks`.
  `TaskFilter.deleted` is `bool | None` (None: both); `series_id` and
  `in_series`. `TaskOutputDTO.series_id`.

### Changed
- Coverage floor 78.5% → 79.2% (488 tests).

## [0.13.0] — 2026-09-26

Undo and deleted tasks as tombstones (Part 2 of the product backlog).
Enterprise 0.9.0 stores them; the CLI 0.15.0 has `undo` and `task restore`.

### Added
- **Undo**: `UndoPreviewUseCase` (what would be undone, whether it can be,
  what goes with it) and `UndoUseCase` (it refuses if the last change is no
  longer the one the preview showed). It walks back in time: each run
  takes back the newest change of the user not undone yet, so a snapshot is
  never restored over a later change. What a change made on its own goes
  with it (the next occurrence of a completed recurring task:
  `TaskCreatedEvent.caused_by`, passed by `create_next_occurrence`).
- **Snapshots**: `Task.snapshot()` (status, dates, title, description,
  priority, energy, context, due date, the whole rule) travels as
  `previous` in the events of every change and is kept in the history;
  `Task.revert_to(now, snapshot, undoes, action)` — undo is not a
  transition, the state machine does not apply. Rules to and from plain
  data: `recurrences/_serial.py` (every rule class, round-trip tested).
- **Tombstones**: `Task.deleted_at`; `mark_deleted` no longer removes the
  task (the use case updates it), `Task.restore` and `RestoreTaskUseCase`
  bring it back. Searches see only live tasks — `find_by_id_prefix(…,
  deleted=True)` and `TaskFilter.deleted` / `ListTasksRequest.deleted` see
  only the deleted ones; `get_by_id` sees both. `purge_deleted(user,
  before)` removes them for good; the delete use case runs it with the new
  preference **`keep_deleted_days`** (30; 0: deleted for good at once).
  `DeleteTaskOutputDTO.kept_days`.
- History: `TaskAction.RESTORED` and `UNDONE`; entries carry `entry_id`
  (their event's id), `previous`, `caused_by` and `undoes`;
  `TaskHistoryRepository.recent` and `caused_by`. Events
  `TaskRestoredEvent`, `TaskUndoneEvent`.

### Fixed
- **Deleting a task its dependents waited on left them blocked forever**:
  `UnlockTaskDependenciesHandler` also reacts to `TaskDeletedEvent`.

### Changed
- `c_application/mappers/history_mapper.py` (entry → DTO), shared.
- Coverage floor 76.8% → 78.5% (480 tests).

## [0.12.0] — 2026-09-26

The task history (Part 1 of the product backlog). Enterprise 0.8.0 stores
it; the CLI 0.14.0 shows it (`axpro task log`).

### Added
- **Every change to a task is an event**: `TaskEditedEvent` (with the
  changed fields, before → after, as text) is now raised — once per edit,
  from a snapshot the use case takes before and after — and so are
  `TaskReopenedEvent`, `TaskArchivedEvent` and `TaskDeletedEvent` (the last
  two existed and were never raised). `TaskCreatedEvent` carries `user_id`.
- **The unit of work writes the history** (`TaskHistoryEntry`: action,
  when, changes, note) in the same transaction as the change and the
  outbox, through the new port `TaskHistoryRepository`
  (`uow.task_history`); `b_domain/events/history.history_entry` maps
  events to entries. The history of a deleted task stays.
- `GetTaskHistoryUseCase` → `TaskHistoryOutputDTO` (oldest first).
- `Task.completed_at` (set on done, cleared on reopen) and
  `TaskOutputDTO.completed_at`.
- **`b_domain/events/registry.EVENT_REGISTRY`**: every event by name, for
  the outbox relay — interfaces use it instead of their own list (an event
  missing from theirs failed on every relay, forever).

### Fixed
- **Rebuilding an event from the outbox turned a `dict`/`list` field into
  text** (`DomainEvent._deserialize_value` fell back to `str`): containers
  now come back as they were.
- The test fakes behave like the real unit of work: the repositories track
  into the UoW's set, and there is an in-memory outbox — events recorded in
  use case tests used to go nowhere.

### Changed
- Coverage floor 75.5% → 76.8% (457 tests; coverage 76.9%).

## [0.11.1] — 2026-09-26

### Fixed
- **An ID prefix with a dash, or longer than the short ID, found nothing**
  (on SQLite, which stores UUIDs without dashes): `45e45de9-55` or the full
  UUID from a card's footer. `IdPrefix` now compares by `hex` (lowercase,
  no dashes) with `matches(id)`; it takes up to 36 characters (a full UUID)
  and only hex digits and dashes (a clearer error than "not found").
  `find_context` and the test fakes use the same rule; enterprise 0.7.2
  does it in SQL.

## [0.11.0] — 2026-09-26

Closes, with enterprise 0.7.1, the item "time entries, behavior metrics and
profiles are created without `_seen_entities`" (enterprise Backlog 01,
Part 5).

### Changed
- **`TimeEntryRepository` is a `BaseRepository`** (like the task, user and
  context ports): the entries it hands out are tracked by the unit of work,
  so an event a `TimeEntry` records reaches the outbox — ready for the
  timers of the product backlog. Implementations take `seen_entities` and
  decorate `add`, `get_*`, `find_by_user` and `search` with
  `@tracks_entity` (the base class refuses them otherwise). Breaks
  implementers: enterprise adapts in 0.7.1.
- Behavior metrics and profiles are not tracked: they are value objects,
  which record no events.

## [0.10.0] — 2026-09-26

`set_pos` works with weekly rules too, and is never silently dropped
(owner's request, 2026-09-26: "the second or the last day of the month or
of the week").

### Added
- **`WeeklyPositionalRule`**: the Nth day of the week — `set_pos` 1 to 7
  from the week's first day, -1 to -7 from its end ("Every week on the last
  day (Sunday)"). The week starts on the user's `week_start` preference
  (`week_start` on the rule: 0 = Monday, 6 = Sunday), passed by create and
  edit (`build_recurrence(…, week_start=)`, `WEEK_STARTS`). RRULE:
  `BYDAY=MO,…,SU;BYSETPOS=n;WKST=…`.
- `BySetPosRequiresWeeklyOrMonthly` (replaces
  `BySetPosRequiresMonthlyFrequency`) and `BySetPosWithWeekdaysInAWeek`.

### Fixed
- **A position was silently ignored** with a weekly rule, with days of the
  month, and with daily/yearly/hourly rules: the task repeated as if it had
  not been given. The factory now builds the weekly rule, or refuses the
  combination saying why (`BySetPosWithMonthDays` has a clearer message).
  Monthly positions are unchanged: alone, the Nth day of the month; with
  weekdays, the Nth of each of them ("the second Friday").

### Changed
- Coverage floor 75.1% → 75.5% (439 tests).

## [0.9.0] — 2026-09-25

Editing a task's recurrence (owner's decision, 2026-09-25: the current
occurrence keeps its due date; the ones after it follow the new rule).

### Added
- `UpdateTaskInputDTO.recurrence` **is applied** (it was ignored) and
  `remove_recurrence` stops repeating. The new rule starts at the task's
  due date — so it keeps its time of day — or at `recurrence.start_date`;
  a task without a due date gets the rule's first occurrence as one.
- `Task.change_recurrence(now, rule | None)`; the rule and the due date must
  share their kind (fixed/floating).
- `c_application/utils/recurrence_input.build_recurrence`: create and edit
  build rules the same way (an end date alone covers that whole day).
- `TaskOutputDTO.recurrence` (`RecurrenceOutputDTO`): the rule as the fields
  it is created from (`RecurrenceMapper`), so an interface can edit it.
- **The update's result previews what comes next**: `next_occurrences` up to
  `days_ahead`, but at least the next one and at most ten
  (`UpdateTaskUseCase.PREVIEW_MAX`), hourly rules included.
  `Task.upcoming_occurrences(…, include_sub_daily=, at_least=)`;
  `TaskMapper.to_output(…, occurrences=)`.

### Fixed
- **`count` never ended a series**: every occurrence carried the full count
  and it was never checked. Now `count` is how many are left, the current
  one included: each new occurrence carries one fewer, the one with 1 is the
  last, and the projection stops there too.

### Changed
- Coverage floor 74.6% → 75.1% (423 tests).

## [0.8.0] — 2026-09-25

What an edit can change, for the CLI's editor mode.

### Added
- `UpdateTaskInputDTO.remove_due_date` and `remove_context`; asking to set
  and to remove the same thing is refused.
- `Task.move_to_context` and `Task.update_energy`.

### Changed
- Coverage floor 74.4% → 74.6% (415 tests).

### Fixed
- `UpdateTaskUseCase` **ignored `context_id` and `energy_level`**: they
  were in the DTO and never applied. The context is found by name or ID
  prefix (`find_context`); the energy takes a name or a number
  (`energy_level: str | int`).

## [0.7.0] — 2026-09-25

Due dates as people type them, a default due time and the projection of
recurring tasks (owner's requests, 2026-09-25). Enterprise and the CLI pick
it up in 0.6.0 and 0.10.0.

### Added
- **`c_application/utils/date_input.py`**: `DateInput` (a datetime, a date
  without time, or a text) and `resolve_date_input(value, today=…)`, which
  takes `2026-10-01`, `2026-10-01 14:00`, `today`, `tomorrow`, `yesterday`
  (optionally followed by `HH:MM`) relative to the user's today. New
  expressions go in its `_DAY_OFFSETS` (or next to it): the use cases do not
  change. Also `local_today`, `at_time`, `end_of_day`, `resolve_horizon`
  (a number of days or a date).
- **Preference `default_due_time`** (`"23:59"`, validated and normalized to
  `HH:MM`; `UserPrefs.default_due_clock`): a due date typed without a time
  gets it — on create, on edit and for a recurrence's first date. A
  recurrence with no first date starts today at that time (before: the
  creation instant). A recurrence's end date typed without a time covers
  that whole day.
- **Preference `days_ahead`** (7, 0 to 366) replaces
  `recurring_tasks_visible_ahead_days` (14, never used; the stored key is
  now ignored, so every account gets 7).
- **Projection of recurring tasks**: `Task.upcoming_occurrences(now, until)`
  — the occurrences after the current one, still ahead, up to `until`;
  hourly rules are not projected. `ListTasksRequest.ahead` (days or a date;
  default `days_ahead`) fills `TaskListOutputDTO.projected` with copies of
  the open recurring tasks at each future date (`TaskOutputDTO.is_projected`,
  the current occurrence's `id`), sorted by date and inside the due filters.
  `GetTaskRequest.ahead` does the same for `next_occurrences`; create and
  update project with `days_ahead`. `RecurrenceRule.is_sub_daily`.

### Changed
- `CreateTaskInputDTO.due_date`, `UpdateTaskInputDTO.due_date`,
  `RecurrenceInputDTO.start_date`/`end_date` and `ListTasksRequest.due_before`
  /`due_after` are `DateInput`; `RecurrenceInputDTO.start_date` is optional.
  In the list filters a date alone means its midnight.
- `TaskOutputDTO.next_occurrences` only has the occurrences after the due
  date, up to the horizon (before: the next five from now, the current one
  included). `TaskMapper.to_output(…, occurrences_until=…)` replaces
  `occurrences_count`; **`GetTaskRequest.n_occurrences` is gone** (`ahead`).
- `ListTasksUseCase` always reads the user (preferences for the time zone
  and the horizon).
- Coverage floor 73.8% → 74.4% (412 tests); coverage reports one decimal.

## [0.6.0] — 2026-09-25

Reopen, archive and cancel a task (Backlog 02, Part 1, last item). For a
recurring task, cancelling skips one occurrence and the series goes on,
unless the cancel ends the series (owner's decision, 2026-09-25).
Enterprise and the CLI pick it up in 0.5.0 and 0.9.0.

### Added
- Use cases `ReopenTaskUseCase`, `ArchiveTaskUseCase` (both take
  `TaskByUserRequest`) and `CancelTaskUseCase` (`CancelTaskInputDTO`, with
  `end_series`); they return a `TaskStatusChangedOutputDTO(task,
  series_ended)`, so an interface can present the change apart from the
  task's detail. Cancelling stops the task's running timers.
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
- Coverage floor 73% → 73.8% (368 tests).

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
