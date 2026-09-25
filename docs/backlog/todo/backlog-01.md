# Backlog 01 — Restarting axiom-core

> Pending work. Index in [README.md](README.md).

## What this backlog is

The core stopped on 2026-04-04 (last commit) with a modernization round done
in June 2026 and never committed. This backlog brings no new functionality:
it **returns the repo to a trustworthy state** — everything committed,
`make check` green, the survey bugs fixed — and makes it presentable as a
showcase. Axiom Flow (new functionality) is [Backlog 02](backlog-02.md).

The 2026-09-24 survey found:

1. **~110 WIP files**: 85 staged and 69 with unstaged changes on top of the
   staged ones. Most of it is mechanical (ruff `UP`, black); the rest is a
   real refactor (see [CHANGELOG](../../../CHANGELOG.md), "Unreleased").
2. **185 tests passing**, black and ruff clean, **mypy with 18 errors**,
   **coverage 57%** — and `make check` requires 95%.
3. **The `unity_of_work` → `unit_of_work` rename broke enterprise**, and the
   CLI with it. Enterprise is adapted in its own Backlog 01; what matters here
   is committing the rename together with the breaking-change note.
4. Some mypy errors are **runtime bugs**, confirmed through the CLI.

## Breakdown

| Part | Scope | Branch | Depends on |
| --- | --- | --- | --- |
| **1** ✅ | Consolidate the WIP into thematic commits | `chore/backlog01-parte1-consolidar-wip` | — |
| **2** ✅ | `make check` green and a real CI | `chore/backlog01-parte2-check-verde` | 1 |
| **3** ✅ | Bugs found in the survey | `fix/backlog01-parte3-bugs-do-levantamento` | 1 |
| **4** ✅ | Contexts: from the entity to the use case | `feat/backlog01-part4-contexts` | 1 |
| **5** | Showcase: README, license, badges | `docs/backlog01-part5-showcase` | 2 |

(Branches of closed parts keep the names they had in git.)

---

## Part 1 — Consolidate the WIP ✅ (2026-09-24)

**In place today:** `git status` with `M`, `MM`, `R`, `D` and `??` mixed
together; the staging was done at some point and the work went on over it.

- [x] Review the WIP and split it into commits. *Resolved on 2026-09-24:*
  splitting by theme inside each file would require `git add -p` and leave
  broken intermediate commits (the changes cross layers). Three commits:
  tooling (`ed813a1`), pre-commit aligned with the project (`68076b2`) and the
  whole modernized code (`64c7791`, 185 tests passing).
- [x] `task_lang_engine_conf.toml` under version control. *Resolved on
  2026-09-24* (`4d21039`): it became `b_domain/engines/task_language_engine.toml`,
  packaged in the wheel; `load_language_engine(path)` became
  `build_language_engine(config, contexts_map)`, with no I/O in the core.
- [x] `TASKS` and the `__main__` out of the domain module. *Resolved on
  2026-09-24:* they went to `d_fake_infra/sample_tasks.py` (local), and the
  simulator reads the TOML itself.
- [x] `version` `0.2.0` and a closed CHANGELOG section. *Resolved on
  2026-09-24.*
- Found along the way: the pre-commit hooks pinned old versions of black and
  ruff and disagreed with `make check`; and `poetry run` in the hooks picked
  the wrong venv when another one was active. *Resolved on 2026-09-24
  (`68076b2`):* local hooks calling `.venv/bin/…` — it was a Part 2 item.

## Part 2 — `make check` green and a real CI ✅ (2026-09-25)

**In place today:** `ci.yml` was copied from base-python-project: it triggers
on `main`/`develop` (the branch is `master`), runs `mypy src` and measures
coverage of `src/arch_pat_with_python`. `.pre-commit-config.yaml` pins old
versions (ruff 0.11, black 25.1, mypy 1.15) that differ from `pyproject`.

- [x] CI: `master` branch; `mypy a_core b_domain c_application`; coverage over
  the three packages (the same command as `make check`). *Resolved on
  2026-09-25 (0.3.10):* the CI runs `make check` itself — there is no second
  command to drift. Python 3.12 only (the build's and the other repos'
  version); 3.13/3.14, which `pyproject` accepts, are not on this machine to
  check first. It has not run yet: the repository does not exist on GitHub.
- [x] Align the pre-commit versions with `pyproject`. *Resolved on
  2026-09-24, in Part 1 (`68076b2`).*
- [x] Get mypy errors to zero (18 in the survey; **15** after Part 3).
  *Resolved on 2026-09-24 (0.3.4):* zero in packages and tests; one of the
  errors hid a runtime bug (`MonthlyAllWeekdaysRule` without `end_date`
  broke when the month turned) and others, wrong port contracts. Groups:
  - `User | None` assigned to `User` after `if not user` (create, get_prefs,
    update_prefs) — typing only;
  - ~~`Priority(str)` / `TaskComplexity(str)`~~ — resolved in Part 3;
  - `ListTasksRequest.ids` → `TaskFilter.ids` (`TaskId` × `UniqueId`);
  - `export_task_handler.py` (`str | None`, `DueDate | None`, `Task | None`);
  - `contexts/activate_context.py` — broken sketch, see Part 4 (removed).
- [x] Coverage: 57% in the survey, **68%** on 2026-09-24 (0.3.4). Set the
  floor **at the real value** (e.g. `--cov-fail-under=57`) so the check goes
  green now, and raise the floor with every part that adds tests. The biggest
  gaps: engines, behavior services, handlers, auth/user use cases. *Resolved
  on 2026-09-25 (0.3.10):* `fail_under = 68` in `[tool.coverage.report]`
  (measured 68.7%), read by `make check` and by the CI; the rule to raise the
  floor is in CLAUDE.md. The gaps are the same — covering them is the job of
  each part that touches them (Backlog 02 touches the engines).
- [x] Try `ruff` with base-python-project's set (`B`, `RUF`) and adopt it if
  the cost is low. *Resolved on 2026-09-25 (0.3.10):* 56 warnings, low cost,
  adopted. 33 were typographic quotes/dashes in docstrings; 12 the autofix
  handled; the rest by hand — `raise … from e` in 5 exception translations,
  2 tests with `pytest.raises(Exception)` and 3 justified exceptions (two
  `ABC` marker classes, the `setattr` mypy requires, `Description("")` as an
  immutable default).
- Afterwards (2026-09-25, 0.3.11): ruff also replaced black as the formatter,
  by the owner's decision.

## Part 3 — Bugs found in the survey ✅ (2026-09-24)

All confirmed by running the CLI against the current core (2026-09-24).
Closed in core 0.2.2 and checked in the CLI (throwaway HOME).

- [x] **Recurrence shown as "-"** for every rule that is not
  `SimpleIntervalRule`. `format_task_recurrence`
  (`c_application/utils/task_utils.py`) looks for `frequency`,
  `by_week_days`, `by_month_days`, `nth_business_day` — names from before the
  2026-03-28 refactor; the current rules have `days_of_week`,
  `days_of_month`, `nth_day` etc. Proposal: each rule knows how to describe
  itself (polymorphic method), and the formatter only builds the sentence.
  One test per rule type. *Resolved on 2026-09-24:* abstract
  `describe_pattern()` on `RecurrenceRule`, one per rule; the formatter adds
  `count`/`until`. The text helpers went to `a_core/text.py` (the domain
  started using them), with the ordinals fixed.
- [x] **`task ls --priority high` fails** ("Invalid priority: high"):
  `ListTasksUseCase` does `Priority(dto.priority)` with text. Same error in
  `TaskComplexity(dto.complexity)` and in `UpdateTaskUseCase`. Convert by
  name. Beware: `Priority.from_string` returns `MEDIUM` for any unknown
  text — too silent for user input; it must fail. *Resolved on 2026-09-24:*
  `LevelEnum.parse` (name or number; unknown → `InvalidValueError` listing the
  options) on `Priority`, `EnergyLevel` and `TaskComplexity`; `from_string`
  removed. Found along the way: update **always** broke without a priority in
  the request (`Priority(None)`), and the `MEDIUM` default of
  `CreateTaskInputDTO` kept the `default_task_priority` preference from
  applying — both fixed.
- [x] **The next occurrence of a recurring task loses attributes.**
  `Task._recreate_task_with_date` calls `Task.create` with only title,
  description, priority, due date, parent and recurrence: `context_id`,
  `required_energy_level`, `complexity`, `depends_on` are lost. And
  `CreateRecurringTaskHandler` overwrites `estimated_duration_minutes` with
  `average_duration_minutes`, which is **0** because nothing computes it.
  *Resolved on 2026-09-24:* everything the user defined for the series
  carries over; the average only replaces the estimate when it exists (> 0).
  Who computes the average is still open — that belongs to learning
  (Backlog 02).
- [x] `whoami` without a login answers "The provided token is invalid."
  (`GetCurrentUserUseCase` raises `InvalidTokenError` for a missing token); a
  missing token must be `NotAuthenticatedError`. *Resolved on 2026-09-24.*
- [x] `LogoutUseCase` invalidates nothing (TODO in the code). Decide: for
  local use, logout = delete the client's token, and the use case says so;
  real revocation only when there is a server (sync/web). *Resolved on
  2026-09-24:* that is the decision; the output carries
  `token_revoked=False` and the token is not validated (an expired one is
  discarded too). Without a token, `NotAuthenticatedError`.

## Part 4 — Contexts: from the entity to the use case ✅ (2026-09-25)

**In place today:** the `Context` entity exists; `UserPrefs.active_context_id`
exists; `CreateTaskUseCase` already inherits the active context. But **there
is no context repository port** on the `UnitOfWork`, `ActivateContextUseCase`
uses `self.current_user` and `uow.contexts` (which do not exist) and
`SwitchContextUseCase` does nothing. Enterprise already has an ORM model and
a mapper.

- [x] `ContextRepository` in `b_domain/ports/repositories/` + a `contexts`
  attribute on the `UnitOfWork` + a fake in `conftest`. *Resolved on
  2026-09-25 (0.4.0):* `add`, `update`, `delete` (must detach the tasks),
  `get_by_id(context_id, user_id)`, `list_by_user`. A user has few contexts,
  so names and ID prefixes are resolved in memory (`find_context`) instead
  of with more repository methods. Enterprise implements it in 0.4.0 (its
  Backlog 01, Part 5).
- [x] Use cases: create, list, rename/delete a context; switch the active
  context (writes `UserPrefs.active_context_id` and emits
  `ContextSwitchedEvent`, which already exists). *Resolved on 2026-09-25
  (0.4.0):* `Create/List/Update/Delete/SwitchContextUseCase`. A context is
  named by its name (ignoring case) or ID prefix; names are unique per user;
  deleting the active context turns the filter off; switching to `None`
  turns it off too. The event's `new_context_id` became optional for that.
- [x] `TaskOutputDTO.context_name/context_icon` filled in (always `None`
  today). *Resolved on 2026-09-25 (0.4.0),* plus `context_id`, in every task
  use case. Found along the way: `CreateTaskUseCase` read `context_id` as a
  UUID, so the CLI's `task add --context work` (a name) always failed; it
  now takes a name or ID prefix, like the list filter.
- [x] Remove the two current sketches. *Resolved on 2026-09-24 (0.3.4),*
  together with mypy: nobody imported them.

## Part 5 — Showcase

**In place today:** the README talks about Python 3.10+ (the project requires
3.12), does not show how to run the tests or the layered architecture with
its rules; **there is no `LICENSE`** (a public repo without a license = all
rights reserved).

- [x] Decide the license with the owner and add `LICENSE`. *Resolved on
  2026-09-24:* a custom license, **Axiom Core License 1.0** (MIT base +
  mandatory attribution of origin and authors + a ban on reselling the core
  as-is). It is not "open source" in the OSI sense, because of clause 3; it
  is permissive *source-available*.
- [ ] README: what the project is, a diagram of the layers, the rules (zero
  dependencies, injected time, events via outbox), usage examples of
  `AxiomDate` and recurrence, how to run `make check`.
- [ ] CI and coverage badges.
- [ ] Review what is public: `diretrizes.md`/`todo.md` stay out of git;
  nothing from the business plan in the README.
