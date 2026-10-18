"""The report counts each occurrence once (product Backlog 08): the totals
once per task, by how it ended; a series judged by its slots — the days its
rule says should have had one — each with one outcome: on time, late,
skipped, missed (nothing recorded, its day gone) or pending (today); hourly
series apart, "N of M".

The fake clock says Thursday 2026-03-05, 12:00 UTC; the user is in UTC and
the week starts on Monday (`report -w`: Monday 2 to Thursday 5).
"""

from datetime import UTC, datetime, timedelta

import pytest

from a_core import UniqueId
from b_domain.entities import Task, User
from b_domain.events.task_events import TaskCancelledEvent, TaskCompletedEvent
from b_domain.value_objects import RecurrenceInterval, TaskId
from b_domain.value_objects.task_history import TaskAction
from c_application.dtos.recurrence_dtos import RecurrenceInputDTO
from c_application.dtos.task_dtos import (
    CancelTaskInputDTO,
    CreateTaskInputDTO,
    TaskByUserRequest,
    TaskOutputDTO,
    UpdateTaskInputDTO,
)
from c_application.handlers.task_handlers.create_recurring_task_handler import (
    CreateRecurringTaskHandler,
)
from c_application.use_cases import (
    CancelTaskUseCase,
    CompleteTaskUseCase,
    CreateTaskUseCase,
    DeleteTaskUseCase,
    ReopenTaskUseCase,
    ReportUseCase,
    SnoozeTaskUseCase,
    UpdateTaskUseCase,
)
from c_application.use_cases.task.delete import DeleteTaskInputDTO
from c_application.use_cases.task.report import (
    ReportOutputDTO,
    ReportRequest,
    SeriesReportDTO,
)
from c_application.use_cases.task.snooze import SnoozeTaskRequest
from tests.conftest import FakeClock, FakeUowFactory, UseCaseDeps

pytestmark = [pytest.mark.asyncio, pytest.mark.uc]


@pytest.fixture
async def user(fake_uow_factory: FakeUowFactory) -> User:
    created = User.create(username="wesley", email="wesley@test.com")
    await fake_uow_factory().users.add(created)
    return created


async def _create(deps: UseCaseDeps, user: User, **kwargs: object) -> TaskOutputDTO:
    return await CreateTaskUseCase(**deps).execute(
        CreateTaskInputDTO(user_id=str(user.id), **kwargs)  # type: ignore[arg-type]
    )


async def _daily(
    deps: UseCaseDeps, user: User, title: str, start: str, **rule: object
) -> TaskOutputDTO:
    return await _create(
        deps,
        user,
        title=title,
        recurrence=RecurrenceInputDTO(
            frequency=rule.pop("frequency", RecurrenceInterval.DAILY),  # type: ignore[arg-type]
            start_date=start,
            **rule,  # type: ignore[arg-type]
        ),
    )


async def _open_one(factory: FakeUowFactory, series_id: str) -> Task:
    """The series' open occurrence."""
    async with factory() as uow:
        [found] = [
            t
            for t in uow.tasks.tasks.values()
            if str(t.series_id) == series_id
            and not t.status.is_closed
            and t.deleted_at is None
        ]
    return found


async def _close(
    deps: UseCaseDeps,
    factory: FakeUowFactory,
    user: User,
    task_id: str,
    *,
    skip: bool = False,
    at: str | None = None,
    end_series: bool = False,
) -> None:
    """Done (``at``: when) or skipped, then what the relay's handler does
    after it (the fake bus runs no handlers): the next occurrence."""
    if skip:
        await CancelTaskUseCase(**deps).execute(
            CancelTaskInputDTO(
                task_id_prefix=task_id, user_id=str(user.id), end_series=end_series
            )
        )
    else:
        await CompleteTaskUseCase(**deps).execute(
            TaskByUserRequest(
                task_id_prefix=task_id, user_id=str(user.id), completed_at=at
            )
        )
    async with factory() as uow:
        last = next(
            e
            for e in await uow.task_history.recent(user.id)
            if str(e.task_id) == task_id
            and e.action in (TaskAction.COMPLETED, TaskAction.CANCELLED)
        )
        closed = await uow.tasks.get_by_id(TaskId.from_string(task_id))
    assert closed is not None
    event: TaskCompletedEvent | TaskCancelledEvent = (
        TaskCompletedEvent(
            id=UniqueId(last.entry_id),
            occurred_at=last.occurred_at,
            task_id=closed.id,
            user_id=user.id,
            estimated_minutes=30,
            actual_minutes=0,
            energy_level_used=closed.required_energy_level,
            task_complexity=closed.complexity,
        )
        if last.action == TaskAction.COMPLETED
        else TaskCancelledEvent(
            id=UniqueId(last.entry_id),
            occurred_at=last.occurred_at,
            task_id=closed.id,
            user_id=user.id,
            end_series=end_series,
        )
    )
    await CreateRecurringTaskHandler(factory()).handle(event)


async def _week(deps: UseCaseDeps, user: User) -> ReportOutputDTO:
    return await ReportUseCase(**deps).execute(
        ReportRequest(user_id=str(user.id), period="week")
    )


def _one(report: ReportOutputDTO, title: str) -> SeriesReportDTO:
    [found] = [s for s in report.series if s.title == title]
    return found


# --- The owner's week ----------------------------------------------------------------


async def test_the_owners_week_counts_each_day_once(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    """Monday done; Tuesday skipped, reopened and done (the fix by hand);
    Wednesday done, and a copy of it the sync made, deleted; today still to
    do. "3 done", not "4 done · 1 skipped"."""
    study = await _daily(use_case_context, user, "Study", "2026-03-02 08:00")
    await _close(
        use_case_context, fake_uow_factory, user, study.id, at="2026-03-02 09:00"
    )
    tuesday = await _open_one(fake_uow_factory, study.id)
    await _close(use_case_context, fake_uow_factory, user, str(tuesday.id), skip=True)
    await ReopenTaskUseCase(**use_case_context).execute(
        TaskByUserRequest(task_id_prefix=str(tuesday.id), user_id=str(user.id))
    )
    await CompleteTaskUseCase(**use_case_context).execute(
        TaskByUserRequest(
            task_id_prefix=str(tuesday.id),
            user_id=str(user.id),
            completed_at="2026-03-03 09:00",
        )
    )
    wednesday = await _open_one(fake_uow_factory, study.id)
    # The sync's copy of Wednesday, deleted by the owner
    async with fake_uow_factory() as uow:
        assert wednesday.due_date is not None
        copy = Task.create(
            now=FakeClock().now(),
            user_id=user.id,
            title=wednesday.title,
            due_date=wednesday.due_date.value,
            series_id=wednesday.series_id,
        )
        await uow.tasks.add(copy)
    await DeleteTaskUseCase(**use_case_context).execute(
        DeleteTaskInputDTO(task_id_prefix=str(copy.id), user_id=str(user.id))
    )
    await _close(
        use_case_context,
        fake_uow_factory,
        user,
        str(wednesday.id),
        at="2026-03-04 09:00",
    )

    report = await _week(use_case_context, user)

    series = _one(report, "Study")
    assert (series.done, series.skipped, series.missed, series.pending) == (3, 0, 0, 1)
    # Each done by 09:00, inside its hour from 08:00
    assert series.timeline == ["on_time", "on_time", "on_time", "pending"]
    assert (series.rate, series.streak) == (1.0, 3)
    # The totals: each task once, by how it ended
    assert (report.done, report.cancelled) == (3, 0)


# --- Missed: nothing recorded --------------------------------------------------------


async def test_days_not_opened_are_missed(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    """Monday done, then nothing: Tuesday's occurrence is still open (kept,
    to be recorded) and Wednesday's was never made."""
    gym = await _daily(use_case_context, user, "Gym", "2026-03-02 07:00")
    await _close(
        use_case_context, fake_uow_factory, user, gym.id, at="2026-03-02 07:30"
    )

    series = _one(await _week(use_case_context, user), "Gym")

    assert series.timeline == ["on_time", "missed", "missed", "pending"]
    assert (series.done, series.missed, series.streak) == (1, 2, 0)
    assert series.rate == pytest.approx(1 / 3)


async def test_a_catch_up_series_misses_the_days_it_skipped(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    """Monday's done only now: catching up, the next one is the first still
    on time (Friday) — Tuesday to Thursday never had one."""
    walk = await _daily(
        use_case_context, user, "Walk", "2026-03-02 07:00", catch_up=True
    )
    await _close(use_case_context, fake_uow_factory, user, walk.id)

    series = _one(await _week(use_case_context, user), "Walk")

    assert series.timeline == ["late", "missed", "missed", "pending"]


async def test_a_series_ended_has_no_slot_after_it(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    pills = await _daily(use_case_context, user, "Pills", "2026-03-02 08:00")
    await _close(
        use_case_context, fake_uow_factory, user, pills.id, at="2026-03-02 08:10"
    )
    tuesday = await _open_one(fake_uow_factory, pills.id)
    await _close(
        use_case_context,
        fake_uow_factory,
        user,
        str(tuesday.id),
        skip=True,
        end_series=True,
    )

    series = _one(await _week(use_case_context, user), "Pills")

    assert series.timeline == ["on_time", "skipped", "none", "none"]
    assert series.rate == 0.5


# --- The rule over time --------------------------------------------------------------


async def test_each_stretch_follows_the_rule_it_had(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    """Weekly on Mondays, done on Monday, then daily from Tuesday on."""
    run = await _daily(
        use_case_context,
        user,
        "Run",
        "2026-02-23 07:00",
        frequency=RecurrenceInterval.WEEKLY,
        by_week_days=[0],
    )
    await _close(
        use_case_context, fake_uow_factory, user, run.id, at="2026-02-23 07:30"
    )
    monday = await _open_one(fake_uow_factory, run.id)
    await _close(
        use_case_context, fake_uow_factory, user, str(monday.id), at="2026-03-02 07:30"
    )
    tuesday = await _open_one(fake_uow_factory, run.id)  # weekly: next Monday
    await UpdateTaskUseCase(**use_case_context).execute(
        UpdateTaskInputDTO(
            task_id_prefix=str(tuesday.id),
            user_id=str(user.id),
            due_date="2026-03-03 07:00",
            recurrence=RecurrenceInputDTO(frequency=RecurrenceInterval.DAILY),
        )
    )

    report = await ReportUseCase(**use_case_context).execute(
        ReportRequest(user_id=str(user.id), start="2026-02-23")
    )

    series = _one(report, "Run")
    # Feb 23 and Mar 2 (weekly); from Mar 3 every day: Tuesday's still open
    days = series.timeline
    assert days[0] == "on_time" and set(days[1:7]) == {"none"}
    assert days[7:] == ["on_time", "missed", "missed", "pending"]


# --- One outcome per slot ------------------------------------------------------------


async def test_a_snooze_keeping_both_fills_its_own_day(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    """A series that catches up: Wednesday's, snoozed to Thursday keeping
    both, done today — it was Wednesday's, late; today has its own."""
    read = await _daily(
        use_case_context, user, "Read", "2026-03-04 20:00", catch_up=True
    )
    await SnoozeTaskUseCase(**use_case_context).execute(
        SnoozeTaskRequest(
            user_id=str(user.id),
            task_id_prefix=read.id,
            to="2026-03-05 20:00",
            keep_both=True,
        )
    )
    await CompleteTaskUseCase(**use_case_context).execute(
        TaskByUserRequest(task_id_prefix=read.id, user_id=str(user.id))
    )

    series = _one(await _week(use_case_context, user), "Read")

    assert series.timeline == ["none", "none", "late", "pending"]


async def test_copies_in_one_slot_count_once_the_best(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    """The sync left two occurrences for Wednesday: one skipped, one done."""
    tea = await _daily(use_case_context, user, "Tea", "2026-03-04 17:00")
    async with fake_uow_factory() as uow:
        stored = await uow.tasks.get_by_id(TaskId.from_string(tea.id))
        assert stored is not None and stored.due_date is not None
        copy = Task.create(
            now=FakeClock().now(),
            user_id=user.id,
            title=stored.title,
            due_date=stored.due_date.value,
            recurrence=stored.recurrence,
            series_id=stored.series_id,
        )
        await uow.tasks.add(copy)
    await CancelTaskUseCase(**use_case_context).execute(
        CancelTaskInputDTO(task_id_prefix=str(copy.id), user_id=str(user.id))
    )
    await CompleteTaskUseCase(**use_case_context).execute(
        TaskByUserRequest(
            task_id_prefix=tea.id, user_id=str(user.id), completed_at="2026-03-04 17:10"
        )
    )

    series = _one(await _week(use_case_context, user), "Tea")

    assert series.timeline[2] == "on_time"
    assert (series.done, series.skipped) == (1, 0)


# --- Hourly, apart -------------------------------------------------------------------


async def test_an_hourly_series_is_counted_apart(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    """Every 2 hours from 06:00; 12:00 now: 4 slots due today, 2 done."""
    water = await _daily(
        use_case_context,
        user,
        "Water",
        "2026-03-05 06:00",
        frequency=RecurrenceInterval.HOURLY,
        interval=2,
    )
    await _close(
        use_case_context, fake_uow_factory, user, water.id, at="2026-03-05 06:05"
    )
    eight = await _open_one(fake_uow_factory, water.id)
    await _close(
        use_case_context, fake_uow_factory, user, str(eight.id), at="2026-03-05 08:05"
    )

    report = await _week(use_case_context, user)

    assert [s.title for s in report.series] == []
    [hourly] = report.hourly
    assert (hourly.title, hourly.done, hourly.slots) == ("Water", 2, 4)
    assert [(d.done, d.slots) for d in hourly.days] == [(0, 0), (0, 0), (0, 0), (2, 4)]
    assert hourly.rate == 0.5


# --- The totals, once per task -------------------------------------------------------


async def test_a_task_counts_once_by_how_it_ended(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    twice = await _create(use_case_context, user, title="Twice")
    turned = await _create(use_case_context, user, title="Turned")
    reopened = await _create(use_case_context, user, title="Reopened")
    gone = await _create(use_case_context, user, title="Gone")
    complete = CompleteTaskUseCase(**use_case_context)
    reopen = ReopenTaskUseCase(**use_case_context)

    def by(task: TaskOutputDTO) -> TaskByUserRequest:
        return TaskByUserRequest(task_id_prefix=task.id, user_id=str(user.id))

    for task in (twice, turned, reopened, gone):
        await complete.execute(by(task))
    await reopen.execute(by(twice))
    await complete.execute(by(twice))
    await reopen.execute(by(turned))
    await CancelTaskUseCase(**use_case_context).execute(
        CancelTaskInputDTO(task_id_prefix=turned.id, user_id=str(user.id))
    )
    await reopen.execute(by(reopened))
    await DeleteTaskUseCase(**use_case_context).execute(
        DeleteTaskInputDTO(task_id_prefix=gone.id, user_id=str(user.id))
    )

    report = await _week(use_case_context, user)

    # Twice once, Turned as cancelled, Reopened (open) and Gone not at all
    assert (report.done, report.cancelled, report.created) == (1, 1, 3)
    assert report.days[-1].done == 1


async def test_a_reopen_after_the_period_still_counts(
    use_case_context: UseCaseDeps, user: User, fake_clock: FakeClock
) -> None:
    """Done last week, reopened today: last week's report no longer has it."""
    task = await _create(use_case_context, user, title="Report")
    fake_clock.set_time(datetime(2026, 2, 26, 12, tzinfo=UTC))
    await CompleteTaskUseCase(**use_case_context).execute(
        TaskByUserRequest(task_id_prefix=task.id, user_id=str(user.id))
    )
    fake_clock.set_time(datetime(2026, 3, 5, 12, tzinfo=UTC))
    await ReopenTaskUseCase(**use_case_context).execute(
        TaskByUserRequest(task_id_prefix=task.id, user_id=str(user.id))
    )

    last_week = await ReportUseCase(**use_case_context).execute(
        ReportRequest(user_id=str(user.id), start="2026-02-23", end="2026-03-01")
    )

    assert last_week.done == 0
    assert last_week.end - last_week.start == timedelta(days=6)
