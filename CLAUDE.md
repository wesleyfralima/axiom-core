# CLAUDE.md — axiom-core

> Business rules and use cases of Axiom Pro. **Public repository**
> (github.com/wesleyfralima/axiom-core) and the author's technical showcase.
> The ecosystem map (enterprise, CLI, web) is in the parent folder's
> `CLAUDE.md` (`../CLAUDE.md`), which lives in a private documentation
> repository. If anything here disagrees with the code, the code wins — and
> the line here gets fixed in the same piece of work.

## Non-negotiable rules

1. **Zero runtime dependencies.** `[tool.poetry.dependencies]` only has
   `python`. Anything that is a framework, database, network or third-party
   library lives in axiom-enterprise, behind a **port** in `b_domain/ports/`.
2. **Nothing from the business plan goes in here** (pricing, paid plan,
   strategy, secrets). The repo is public.
3. **Self-contained.** Do not depend on `base-python-project`; copying and
   adapting from it is fine.
4. **Time is injected.** Domain methods receive `now: datetime`; use cases
   use `self.clock.now()` (`ClockProvider`). Never `datetime.now()` in a
   business rule (legacy exceptions: `Entity`/`DomainEvent` defaults).
5. **Side effects become events.** The use case changes the entity; the
   entity records the `DomainEvent`; the `UnitOfWork` writes it to the Outbox;
   a handler (`c_application/handlers/`) reacts. E.g. completing a task →
   unblock dependents and create the next occurrence.
6. **An API change used by enterprise/CLI only closes once they are adapted.**
7. **Everything in English** — code, names, comments, docstrings, messages,
   tests, docs and commit messages. Multi-language support is a future
   feature (see the CLI's Backlog 02); until then, the only non-English text
   allowed is language data meant to understand user input (e.g. the `pt`
   sections of `task_language_engine.toml`).

## Layers

The letter in the name makes the dependency order visible in `ls`. A layer
only imports from the ones before it.

| Folder | Role |
| --- | --- |
| `a_core/` | Generic base, nothing Axiom-specific: `ddd/` (`Entity`, `ValueObject`, `SimpleValueObject`, `TextValueObject`, `UniqueId`, `IdPrefix`, `DomainEvent`), `persistence/` (`BaseRepository`, `@tracks_entity`), `application/` (`DTO`, `InputDTO`, `OutputDTO`, `PaginatedResponse`), `exceptions.py`, `text.py` (ordinals, English lists) |
| `b_domain/` | `entities/` (Task, User, Context, TimeEntry, OutboxEvent), `value_objects/` (dates, enums, recurrences, texts, ids, flow state, behavior profile/metrics, reward), `events/`, `exceptions/`, `ports/`, `services/`, `engines/` |
| `c_application/` | `use_cases/` (auth, task, user, contexts), `handlers/` + `wiring.py`, `dtos/`, `mappers/` (entity → OutputDTO), `utils/` |

Outside the package, **local and gitignored**: `diretrizes.md` (the Axiom
Flow vision), `todo.md` (the "master" backlog from March 2026) and
`d_fake_infra/` (in-memory repositories + an interactive FlowEngine
simulator: `python -m d_fake_infra`).

## Where to look for things

- **Use case contract:** `b_domain/ports/use_case.py` — `UseCase[TReq, TResp]`
  receives `uow_factory` and `clock`; each `async with self.uow as uow:` opens
  a new transaction; `execute` is `async`.
- **Transaction + outbox:** `b_domain/ports/unit_of_work.py`. Concrete
  repositories inherit `BaseRepository` and decorate with `@tracks_entity`
  every method that returns an entity — that is how the UoW finds the events.
  `__init_subclass__` enforces it when the class is defined.
- **Handler registration:** `c_application/handlers/wiring.py` —
  `register_essential_handlers` (dependency unblocking, recurrence) and
  `register_optional_handlers` (metrics + learning; receives `None` and
  registers nothing when the product does not turn them on).
- **Dates:** `b_domain/value_objects/dates.py`. `AxiomDate.fixed` = an instant
  (aware, UTC); `AxiomDate.floating` = wall-clock time + source timezone
  (naive). A floating task requires a floating recurrence, and vice versa.
- **Recurrences:** `b_domain/value_objects/recurrences/` — one class per rule,
  `_base.py` with the contract, `_factory.py` builds from the
  `RecurrenceInputDTO`. Each rule describes itself (`describe_pattern()`); a
  new rule must implement that method.
- **Level input from the user:** `Priority`, `EnergyLevel` and
  `TaskComplexity` inherit `LevelEnum`; convert text/numbers with
  `.parse(...)` (fails with `InvalidValueError`), never with `Priority(text)`.
- **Engines (no use case yet):** `b_domain/engines/flow_engine.py`
  (`FlowEngine.get_next_action` → `FlowDecision`) and
  `b_domain/engines/task_language_engine.py`
  (`build_language_engine(config, contexts_map)` →
  `TaskLanguageEngine.infer(text, now, lang)`). The latter's default
  configuration is `b_domain/engines/task_language_engine.toml`, packaged;
  the caller reads it (`importlib.resources` + `tomllib`), never the core.
- **Short IDs:** dashes and case never matter — compare with
  `IdPrefix.matches(id)` / `IdPrefix.hex`, never `str(id).startswith`.
  Task use cases receive a UUID **prefix** (`IdPrefix`) and
  resolve it with `c_application/utils/task_utils.find_task` (scoped by
  user; older use cases still go through
  `TaskRepository.task_ids_from_id_prefixes`); ambiguity is an error.
- **Dates the user types:** `c_application/utils/date_input.py` —
  every use case that takes a date from the user takes a `DateInput` and
  resolves it there against the user's today (`local_today(clock.now(),
  tz)`); a date alone gets `default_due_time` (due dates) or midnight (list
  filters). New expressions go there, not in the use cases.
- **Projection:** `Task.upcoming_occurrences(now, until)` (not hourly);
  `ListTasksUseCase` fills `projected` and `GetTaskUseCase`
  `next_occurrences` up to `ahead` or the `days_ahead` preference.
- **Positions (`set_pos`):** weekly alone = the Nth day of the week (from
  the user's `week_start`); monthly alone = the Nth day of the month;
  monthly with weekdays = the Nth of each. Any other combination is refused
  by `RecurrenceFactory` — never ignored.
- **Recurrence edit:** `UpdateTaskUseCase._repeat_by` — the due date stays,
  the rule starts at it (`build_recurrence`, shared with create), the next
  occurrences follow it. `count` = occurrences left, this one included.
- **History:** a change to a task raises an event; the UoW turns task
  events into `TaskHistoryEntry` (`b_domain/events/history.py`) and writes
  them with the outbox, same transaction. A new kind of change needs its
  event (with `task_id` and `user_id`) and a line in `_ACTIONS`. New events
  of any kind are picked up by `b_domain/events/registry.py` on their own.
- **Undo and tombstones:** `c_application/use_cases/task/undo.py`. A change's
  event carries `previous=task.snapshot()`; undo restores it with
  `Task.revert_to` (no state machine). A delete is a tombstone
  (`deleted_at`): searches see only live tasks unless asked for deleted
  ones; `get_by_id` sees both; `purge_deleted` is final.
- **Task lifecycle:** the state machine is `TaskStatus._get_transitions`
  (`b_domain/value_objects/enums.py`). Closed = done, cancelled, archived;
  only done/cancelled can be reopened or archived; archived is terminal and
  leaves even the full list. Closing a recurring occurrence (done, or
  cancelled without `end_series`) creates the next one through the event;
  a reopened occurrence becomes a one-off.
- **Business days:** `b_domain/value_objects/work_calendar.py`
  (`WorkCalendar`: the `work_days` preference, then the `holiday_region`'s
  holidays through the `HolidayProvider` port — `uow.holidays` — then the
  user's own days, `CalendarDay`, in `uow.calendar_days`; each wins over the
  one before). A rule that counts business days does not store them: code
  that computes occurrences calls
  `c_application/utils/work_calendar.use_work_calendar` first (create, edit,
  list, show, the next occurrence, the calendar export do). Use cases in
  `c_application/use_cases/work_calendar/` (the regions to choose from:
  `ListHolidayRegionsUseCase`, search in `utils/holiday_regions.py`). A
  region's holiday can be skipped every year by name (`skipped_holidays`,
  `SkipHolidayUseCase`).
- **Tags and the inbox:** `Task.tags` (normalized by
  `b_domain/value_objects/texts.normalize_tags`); the inbox is not a field
  but a view — open tasks with no due date and no context
  (`ListTasksRequest.inbox`); `use_active_context=False` on create sends a
  task there.
- **Sync between devices:** `b_domain/value_objects/sync.py` (`Hlc`,
  `SyncOperation`, `FieldKey`) and `b_domain/services/sync_merge.py`
  (`plan_merge`: last writer per field, final deletions). Sync carries
  results, not commands: a device applies the plan straight to its data —
  no use case, no event, no history entry. The device's side is the
  `SyncStore` port (`uow.sync`), which records every change as operations
  on its own once the device joined; the server is the `SyncTransport`
  port; the use cases are in `c_application/use_cases/sync/` (join, run,
  status, devices). `undo` skips the changes of other devices
  (`TaskHistoryEntry.device_id`). The design is in the product backlog
  (`../docs/backlog/todo/backlog-01.md`, Part 5).
- **The sync server:** `b_domain/ports/sync_server_store.py`
  (`SyncServerStore`) and `c_application/use_cases/sync_server/` (invite,
  account, device, push, pull, devices). They take the store and the clock
  (`SyncServerUseCase`), not a unit of work: the server has no task schema.
- **Contexts:** `b_domain/entities/context.py`, port
  `ContextRepository`, use cases in `c_application/use_cases/context/`. A
  context is named by its name (ignoring case) or ID prefix —
  `c_application/utils/context_utils.py:find_context`, also used by the
  task use cases. The active one lives in `UserPrefs.active_context_id` and
  only changes through `User.switch_context` (which emits
  `ContextSwitchedEvent`).

The full inventory (what exists, what is missing, what is broken) is in
`../docs/inventory.md`.

## Code conventions

- Python 3.12, modern syntax: `X | None`, PEP 695 generics
  (`class UseCase[TReq, TResp]`), `StrEnum`/`IntEnum`, `datetime.UTC`.
- Entities: `@dataclass(kw_only=True, eq=False)` + a `create(...)` factory.
  Value objects: `@dataclass(frozen=True)`; methods that "change" return a
  copy.
- Google-style docstrings (Args / Returns / Raises).
- Business exceptions inherit `DomainException` (`a_core/exceptions.py`) and
  live in `b_domain/exceptions/` by subject.
- ruff for formatting and linting (`E, F, I, UP, B, RUF`), line length 88;
  strict mypy (`disallow_untyped_defs`) on `a_core`, `b_domain`,
  `c_application` and `tests` — it is at zero; commits no longer use
  `SKIP=mypy`.

## Commands

The pre-commit hooks (`.pre-commit-config.yaml`) call the tools from the
repo's own `.venv`, so they never disagree with `make check`. Do not use
`poetry run` in the hooks: with another venv active in the terminal (VSCode
activates one on its own), Poetry uses the wrong venv.

```bash
make check      # ruff format --check, ruff, mypy, pytest with the coverage floor (CI runs this)
make test       # pytest only
make coverage   # report in htmlcov/
make lint-fix   # ruff --fix
make format     # ruff format
```

Tests live in `tests/a_unit` (marker `unit`), `tests/b_integration` and
`tests/c_system` (empty). The repository, UoW and clock fakes are in
`tests/conftest.py` (`fake_uow_factory`, `fake_clock`, `use_case_context`).

## Workflow

1. One branch per piece of work: `feat/backlogNN-partN-short-name` (or
   `fix/…`, `chore/…`, `docs/…`).
2. Commit on the branch; `merge --no-ff` into `master`. Push only when the
   owner asks.
3. In the same commit as the work: bump `version` in `pyproject.toml`
   (feature → `0.x.0`; fix → `0.x.y`) and write the `CHANGELOG.md` entry.
4. `make check` green before merging. The coverage floor (`fail_under` in
   `pyproject.toml`) is the real coverage: whoever adds tests raises the floor
   in the same commit.

### docs/backlog/todo/ and docs/backlog/done/

Pending work and history live in **one file per goal**, and each folder has a
`README.md` that is only the index. A file only moves to `done/` when it is
100% done, whole, with "resolved on …" on every item; while any item is open
it stays in `todo/` (`[x]` items included). `done/` is not edited
retroactively. If a piece of work closes an item in another file, close it
there too.

## Current state (2026-09-26)

- Version `0.22.0`: WIP consolidated (Backlog 01, Part 1), `make check` green
  and CI (Part 2), survey bugs (Part 3), contexts (Part 4), license (Part 5,
  1st item), what the CLI asked for daily use (list only open tasks, edit due
  date, validate preferences), and the whole repo in English with ruff as the
  formatter; the active context can limit the task list (0.5.0); reopen,
  archive and cancel a task (0.6.0, Backlog 02, Part 1); dates as typed,
  `default_due_time` and the projection of recurring tasks (0.7.0); an
  edit changes context and energy and can remove the due date or context
  (0.8.0); recurrence edit and `count` fixed (0.9.0); weekly `set_pos`
  (0.10.0); time entries tracked by the UoW (0.11.0); the task history
  (0.12.0); undo and tombstones (0.13.0); reports and series (0.14.0);
  timers and estimates (0.15.0); business days: work days, a region's
  holidays and the user's own days (0.16.0); the regions to choose from
  (0.17.0); tags, the inbox, skipping a holiday by name (0.18.0); the
  sync rule: clock, operation, merge (0.19.0); the sync ports and use
  cases (0.20.0); the sync server's side (0.21.0); the device list as a DTO (0.22.0).
  Backlog 01 only lacks the rest of Part 5 (showcase).
- 709 tests passing; **`make check` green**: mypy at zero (packages and
  tests), ruff with `B`/`RUF`, coverage 85.1% over a 85.0% floor.
- CI (`.github/workflows/ci.yml`) runs `make check` on `master` and on PRs;
  it has not really run yet because the repository does not exist on GitHub.
