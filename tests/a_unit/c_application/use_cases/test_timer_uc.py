"""Timers (start, pause), estimates, and what the report makes of them.

The fake clock starts on Thursday 2026-03-05, 12:00 UTC and is moved by hand.
"""

from datetime import UTC, datetime, timedelta

import pytest

from a_core import InvalidStateTransition
from a_core.exceptions import ValidationException
from b_domain.entities import User
from b_domain.exceptions import TimerRunningError, TookPastTimerError
from b_domain.ports.repositories.filters import TimeEntryFilter
from b_domain.value_objects import TaskId, TaskStatus
from c_application.dtos.task_dtos import (
    CreateTaskInputDTO,
    GetTaskRequest,
    TaskByUserRequest,
    TaskHistoryRequest,
    TaskOutputDTO,
    UpdateTaskInputDTO,
)
from c_application.use_cases import (
    CompleteTaskUseCase,
    CreateTaskUseCase,
    GetTaskHistoryUseCase,
    GetTaskUseCase,
    PauseTaskUseCase,
    ReportUseCase,
    StartTaskUseCase,
    UndoPreviewUseCase,
    UndoUseCase,
    UpdateTaskUseCase,
)
from c_application.use_cases.task.report import ReportRequest
from c_application.use_cases.task.timer import TimerRequest
from c_application.use_cases.task.undo import UndoRequest
from tests.conftest import FakeClock, FakeUowFactory, UseCaseDeps

pytestmark = [pytest.mark.asyncio, pytest.mark.uc]

NOON = datetime(2026, 3, 5, 12, 0, tzinfo=UTC)


@pytest.fixture
async def user(fake_uow_factory: FakeUowFactory) -> User:
    created = User.create(username="wesley", email="wesley@test.com")
    await fake_uow_factory().users.add(created)
    return created


async def _create(deps: UseCaseDeps, user: User, **kwargs: object) -> TaskOutputDTO:
    return await CreateTaskUseCase(**deps).execute(
        CreateTaskInputDTO(user_id=str(user.id), **{"title": "Write", **kwargs})  # type: ignore[arg-type]
    )


def _by(user: User, task: TaskOutputDTO) -> TaskByUserRequest:
    return TaskByUserRequest(task_id_prefix=task.id[:8], user_id=str(user.id))


def _timer(user: User, task: TaskOutputDTO, **kwargs: object) -> TimerRequest:
    return TimerRequest(task_id_prefix=task.id[:8], user_id=str(user.id), **kwargs)  # type: ignore[arg-type]


def _at(clock: FakeClock, minutes: int) -> None:
    clock.set_time(NOON + timedelta(minutes=minutes))


async def _task(fake_uow_factory: FakeUowFactory, task: TaskOutputDTO):  # type: ignore[no-untyped-def]
    async with fake_uow_factory() as uow:
        return await uow.tasks.get_by_id(TaskId.from_string(task.id))


async def _undo(deps: UseCaseDeps, user: User) -> str:
    preview = await UndoPreviewUseCase(**deps).execute(
        UndoRequest(user_id=str(user.id))
    )
    done = await UndoUseCase(**deps).execute(
        UndoRequest(user_id=str(user.id), entry_id=preview.entry_id)
    )
    return done.action


async def test_start_pause_start_done_counts_every_session(
    use_case_context: UseCaseDeps, user: User, fake_clock: FakeClock
) -> None:
    task = await _create(use_case_context, user)

    started = await StartTaskUseCase(**use_case_context).execute(_timer(user, task))
    assert started.task.status == TaskStatus.IN_PROGRESS
    assert started.task.running_since == NOON

    _at(fake_clock, 25)
    paused = await PauseTaskUseCase(**use_case_context).execute(_timer(user, task))
    assert paused.task.status == TaskStatus.PAUSED
    assert paused.session_minutes == 25
    assert paused.task.running_since is None

    _at(fake_clock, 60)
    await StartTaskUseCase(**use_case_context).execute(_timer(user, task))
    _at(fake_clock, 70)
    done = await CompleteTaskUseCase(**use_case_context).execute(_by(user, task))

    shown = await GetTaskUseCase(**use_case_context).execute(
        GetTaskRequest(task_id_prefix=task.id[:8], user_id=str(user.id))
    )
    assert done.completed_task.status == TaskStatus.DONE
    assert shown.time_spent_minutes == 35  # 25 + 10


async def test_one_timer_at_a_time_is_enforced(
    use_case_context: UseCaseDeps,
    user: User,
    fake_clock: FakeClock,
    fake_uow_factory: FakeUowFactory,
) -> None:
    """The owner, 2026-10-18: a start is refused while any timer runs — it
    is paused first, never on its own."""
    first = await _create(use_case_context, user, title="First")
    second = await _create(use_case_context, user, title="Second")
    await StartTaskUseCase(**use_case_context).execute(_timer(user, first))

    _at(fake_clock, 15)
    for task in (second, first):
        with pytest.raises(TimerRunningError, match="'First' is running") as refused:
            await StartTaskUseCase(**use_case_context).execute(_timer(user, task))
        assert refused.value.task_id == first.id and refused.value.since == NOON

    back = await _task(fake_uow_factory, second)
    assert back is not None and back.status == TaskStatus.PENDING

    # Undoing a start throws its session away
    assert await _undo(use_case_context, user) == "started"
    async with fake_uow_factory() as uow:
        assert await uow.time_entries.get_active_for_user(user.id) is None


async def test_undoing_a_pause_runs_the_same_session_again(
    use_case_context: UseCaseDeps,
    user: User,
    fake_clock: FakeClock,
    fake_uow_factory: FakeUowFactory,
) -> None:
    task = await _create(use_case_context, user)
    await StartTaskUseCase(**use_case_context).execute(_timer(user, task))
    _at(fake_clock, 20)
    await PauseTaskUseCase(**use_case_context).execute(_timer(user, task))

    assert await _undo(use_case_context, user) == "paused"

    back = await _task(fake_uow_factory, task)
    assert back is not None and back.status == TaskStatus.IN_PROGRESS
    async with fake_uow_factory() as uow:
        [session] = await uow.time_entries.get_actives_for_task(back.id)
    assert session.start_time == NOON


async def test_what_cannot_start_or_pause(
    use_case_context: UseCaseDeps, user: User
) -> None:
    blocker = await _create(use_case_context, user, title="Before")
    after = await _create(
        use_case_context, user, title="After", depends_on={blocker.id}
    )

    with pytest.raises(InvalidStateTransition, match="waiting on other tasks"):
        await StartTaskUseCase(**use_case_context).execute(_timer(user, after))
    with pytest.raises(InvalidStateTransition, match="no timer running"):
        await PauseTaskUseCase(**use_case_context).execute(_timer(user, blocker))
    await StartTaskUseCase(**use_case_context).execute(_timer(user, blocker))
    with pytest.raises(TimerRunningError, match="'Before' is running"):
        await StartTaskUseCase(**use_case_context).execute(_timer(user, blocker))


async def test_estimates_default_edit_and_learn(
    use_case_context: UseCaseDeps,
    user: User,
    fake_clock: FakeClock,
    fake_uow_factory: FakeUowFactory,
) -> None:
    default = await _create(use_case_context, user)
    assert default.estimated_minutes == 60  # default_task_duration_minutes
    task = await _create(use_case_context, user, title="Short", estimated_minutes=15)
    assert task.estimated_minutes == 15

    edited = await UpdateTaskUseCase(**use_case_context).execute(
        UpdateTaskInputDTO(
            task_id_prefix=task.id[:8], user_id=str(user.id), estimated_minutes=20
        )
    )
    assert edited.estimated_minutes == 20

    await StartTaskUseCase(**use_case_context).execute(_timer(user, task))
    _at(fake_clock, 40)
    await CompleteTaskUseCase(**use_case_context).execute(_by(user, task))
    back = await _task(fake_uow_factory, task)
    assert back is not None
    assert (back.average_duration_minutes, back.success_count) == (40, 1)


async def test_the_report_has_time_accuracy_and_best_hours(
    use_case_context: UseCaseDeps,
    user: User,
    fake_clock: FakeClock,
) -> None:
    for n in range(5):
        _at(fake_clock, n * 60)
        task = await _create(
            use_case_context, user, title=f"Task {n}", estimated_minutes=30
        )
        await StartTaskUseCase(**use_case_context).execute(_timer(user, task))
        _at(fake_clock, n * 60 + 45)  # every one takes 45 minutes
        await CompleteTaskUseCase(**use_case_context).execute(_by(user, task))
    _at(fake_clock, 6 * 60)

    report = await ReportUseCase(**use_case_context).execute(
        ReportRequest(user_id=str(user.id))
    )

    # Accuracy rows are named by context: the period's label is not one of them
    assert report.period == "last 7 days"
    assert report.time_spent_minutes == 5 * 45
    assert [(c.label, c.count) for c in report.time_by_context] == [("none", 225)]
    [overall, *_] = report.accuracy
    assert (overall.label, overall.tasks) == ("all", 5)
    assert (overall.estimated_minutes, overall.actual_minutes) == (150, 225)
    assert len(report.best_hours) == 3


# --- When it started, when it stopped (product Backlog 09) -------------------------


async def test_a_forgotten_timer_stopped_when_it_really_was(
    use_case_context: UseCaseDeps,
    user: User,
    fake_clock: FakeClock,
    fake_uow_factory: FakeUowFactory,
) -> None:
    """The owner's night: started at 20:00, never paused; the morning after,
    paused at 23:10 the night before, and started again now."""
    task = await _create(use_case_context, user)
    fake_clock.set_time(datetime(2026, 3, 4, 20, 0, tzinfo=UTC))
    await StartTaskUseCase(**use_case_context).execute(_timer(user, task))
    fake_clock.set_time(NOON)  # the next day, 16h later

    paused = await PauseTaskUseCase(**use_case_context).execute(
        _timer(user, task, at="yesterday 23:10")
    )
    assert (paused.session_minutes, paused.stopped_at) == (
        190,
        datetime(2026, 3, 4, 23, 10, tzinfo=UTC),
    )
    again = await StartTaskUseCase(**use_case_context).execute(_timer(user, task))

    assert again.started_at == NOON
    assert again.task.time_spent_minutes == 190
    log = await GetTaskHistoryUseCase(**use_case_context).execute(
        TaskHistoryRequest(task_id_prefix=task.id[:8], user_id=str(user.id))
    )
    assert [e.note for e in log.entries if e.action == "paused"] == ["190 min"]


async def test_a_start_may_be_before_the_task_was_created(
    use_case_context: UseCaseDeps, user: User, fake_clock: FakeClock
) -> None:
    task = await _create(use_case_context, user)  # created at noon

    started = await StartTaskUseCase(**use_case_context).execute(
        _timer(user, task, at="11:20")
    )

    assert started.started_at == datetime(2026, 3, 5, 11, 20, tzinfo=UTC)
    assert started.task.running_since == datetime(2026, 3, 5, 11, 20, tzinfo=UTC)


@pytest.mark.parametrize(
    ("typed", "match"),
    [
        ("13:00", "cannot be started in the future"),
        ("2026-03-04", "needs a time of day"),
    ],
)
async def test_what_a_start_moment_refuses(
    use_case_context: UseCaseDeps, user: User, typed: str, match: str
) -> None:
    task = await _create(use_case_context, user)
    with pytest.raises(ValidationException, match=match):
        await StartTaskUseCase(**use_case_context).execute(_timer(user, task, at=typed))


async def test_no_time_counts_twice(
    use_case_context: UseCaseDeps, user: User, fake_clock: FakeClock
) -> None:
    """Timed 09:00 to 10:00; a start at 09:30 (or 08:00) would run over it."""
    first = await _create(use_case_context, user, title="First")
    second = await _create(use_case_context, user, title="Second")
    start = StartTaskUseCase(**use_case_context)
    await start.execute(_timer(user, first, at="09:00"))
    await PauseTaskUseCase(**use_case_context).execute(_timer(user, first, at="10:00"))

    for typed in ("09:30", "08:00"):
        with pytest.raises(
            ValidationException,
            match="'First' was timed from 2026-03-05 09:00 to 2026-03-05 10:00",
        ):
            await start.execute(_timer(user, second, at=typed))
    started = await start.execute(_timer(user, second, at="10:00"))
    assert started.started_at == datetime(2026, 3, 5, 10, 0, tzinfo=UTC)


async def test_a_pause_moment_is_after_its_start_and_never_ahead(
    use_case_context: UseCaseDeps, user: User
) -> None:
    task = await _create(use_case_context, user)
    await StartTaskUseCase(**use_case_context).execute(_timer(user, task, at="11:00"))
    pause = PauseTaskUseCase(**use_case_context)

    with pytest.raises(ValidationException, match="started at 2026-03-05 11:00"):
        await pause.execute(_timer(user, task, at="10:30"))
    with pytest.raises(ValidationException, match="cannot be paused in the future"):
        await pause.execute(_timer(user, task, at="12:30"))


async def test_a_discarded_timer_counts_nowhere_and_is_kept(
    use_case_context: UseCaseDeps,
    user: User,
    fake_clock: FakeClock,
    fake_uow_factory: FakeUowFactory,
) -> None:
    """Started, then something urgent: not even a minute counts."""
    task = await _create(use_case_context, user, estimated_minutes=30)
    await StartTaskUseCase(**use_case_context).execute(_timer(user, task))
    _at(fake_clock, 12)

    dropped = await PauseTaskUseCase(**use_case_context).execute(
        _timer(user, task, discard=True)
    )

    assert dropped.discarded and dropped.session_minutes == 12
    assert dropped.task.time_spent_minutes == 0
    async with fake_uow_factory() as uow:
        [kept] = await uow.time_entries.search(
            TimeEntryFilter(task_id=TaskId.from_string(task.id))
        )
    assert kept.discarded and kept.elapsed_minutes() == 12
    log = await GetTaskHistoryUseCase(**use_case_context).execute(
        TaskHistoryRequest(task_id_prefix=task.id[:8], user_id=str(user.id))
    )
    assert log.entries[-1].note == "Timer discarded: 12 min not counted."

    # Done: nothing measured, nothing learnt; the report has no time
    _at(fake_clock, 20)
    await CompleteTaskUseCase(**use_case_context).execute(_by(user, task))
    back = await _task(fake_uow_factory, task)
    assert back is not None and back.success_count == 0
    report = await ReportUseCase(**use_case_context).execute(
        ReportRequest(user_id=str(user.id))
    )
    assert report.time_spent_minutes == 0


async def test_undoing_a_discard_counts_the_session_again(
    use_case_context: UseCaseDeps, user: User, fake_clock: FakeClock
) -> None:
    task = await _create(use_case_context, user)
    await StartTaskUseCase(**use_case_context).execute(_timer(user, task))
    _at(fake_clock, 10)
    await PauseTaskUseCase(**use_case_context).execute(_timer(user, task, discard=True))

    assert await _undo(use_case_context, user) == "paused"

    _at(fake_clock, 30)
    shown = await GetTaskUseCase(**use_case_context).execute(
        GetTaskRequest(task_id_prefix=task.id[:8], user_id=str(user.id))
    )
    assert shown.running_since == NOON and shown.time_spent_minutes == 30


# --- Done with a timer: --took and --at (product Backlog 09, Part 2) --------------


def _done(user: User, task: TaskOutputDTO, **kwargs: object) -> TaskByUserRequest:
    return TaskByUserRequest(task_id_prefix=task.id[:8], user_id=str(user.id), **kwargs)  # type: ignore[arg-type]


async def _sessions(factory: FakeUowFactory, task: TaskOutputDTO) -> list[int]:
    async with factory() as uow:
        found = await uow.time_entries.search(
            TimeEntryFilter(task_id=TaskId.from_string(task.id))
        )
    return [e.counted_minutes() for e in sorted(found, key=lambda e: e.start_time)]


async def test_took_stops_a_running_timer_where_it_adds_up(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    """2h yesterday, started at 10:00 today, `--took 3h`: it stops at 11:00."""
    task = await _create(use_case_context, user)
    start = StartTaskUseCase(**use_case_context)
    pause = PauseTaskUseCase(**use_case_context)
    await start.execute(_timer(user, task, at="yesterday 09:00"))
    await pause.execute(_timer(user, task, at="yesterday 11:00"))
    await start.execute(_timer(user, task, at="10:00"))

    await CompleteTaskUseCase(**use_case_context).execute(
        _done(user, task, took_minutes=180)
    )

    assert await _sessions(fake_uow_factory, task) == [120, 60]
    back = await _task(fake_uow_factory, task)
    assert back is not None and back.took_minutes == 180


async def test_took_under_what_was_timed_stops_it_at_its_start(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    task = await _create(use_case_context, user)
    await StartTaskUseCase(**use_case_context).execute(
        _timer(user, task, at="yesterday 09:00")
    )
    await PauseTaskUseCase(**use_case_context).execute(
        _timer(user, task, at="yesterday 11:00")
    )
    await StartTaskUseCase(**use_case_context).execute(_timer(user, task, at="10:00"))

    await CompleteTaskUseCase(**use_case_context).execute(
        _done(user, task, took_minutes=60)
    )

    assert await _sessions(fake_uow_factory, task) == [120, 0]


@pytest.mark.parametrize(
    ("started", "at", "match"),
    [
        (
            "11:50",
            None,
            "started 10 min before it was done: 60 min would stop it in the future",
        ),
        (
            "09:00",
            "10:00",
            "60 min before it was done: 120 min would stop it after it was done",
        ),
    ],
)
async def test_took_past_the_timer_is_refused(
    use_case_context: UseCaseDeps,
    user: User,
    started: str,
    at: str | None,
    match: str,
) -> None:
    task = await _create(use_case_context, user)
    await StartTaskUseCase(**use_case_context).execute(_timer(user, task, at=started))

    with pytest.raises(TookPastTimerError, match=match) as refused:
        await CompleteTaskUseCase(**use_case_context).execute(
            _done(
                user,
                task,
                took_minutes=60 if at is None else 120,
                completed_at=at,
            )
        )
    assert refused.value.task_id == task.id


async def test_took_with_a_timer_stopped_or_none_changes_no_session(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    timed = await _create(use_case_context, user, title="Timed")
    await StartTaskUseCase(**use_case_context).execute(_timer(user, timed, at="09:00"))
    await PauseTaskUseCase(**use_case_context).execute(_timer(user, timed, at="09:40"))
    untimed = await _create(use_case_context, user, title="Untimed")
    complete = CompleteTaskUseCase(**use_case_context)

    await complete.execute(_done(user, timed, took_minutes=15))
    await complete.execute(_done(user, untimed, took_minutes=15))

    assert await _sessions(fake_uow_factory, timed) == [40]
    assert await _sessions(fake_uow_factory, untimed) == []
    for task in (timed, untimed):
        back = await _task(fake_uow_factory, task)
        assert back is not None and back.took_minutes == 15


async def test_done_at_stops_a_running_timer_there(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    task = await _create(use_case_context, user)
    await StartTaskUseCase(**use_case_context).execute(_timer(user, task, at="09:00"))

    await CompleteTaskUseCase(**use_case_context).execute(
        _done(user, task, completed_at="10:30")
    )

    assert await _sessions(fake_uow_factory, task) == [90]


async def test_a_discarded_session_does_not_stand_in_the_way(
    use_case_context: UseCaseDeps, user: User
) -> None:
    first = await _create(use_case_context, user, title="First")
    second = await _create(use_case_context, user, title="Second")
    await StartTaskUseCase(**use_case_context).execute(_timer(user, first, at="11:00"))
    await PauseTaskUseCase(**use_case_context).execute(
        _timer(user, first, discard=True)
    )

    started = await StartTaskUseCase(**use_case_context).execute(
        _timer(user, second, at="11:30")
    )

    assert started.started_at == datetime(2026, 3, 5, 11, 30, tzinfo=UTC)
