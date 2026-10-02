"""Timers (start, pause), estimates, and what the report makes of them.

The fake clock starts on Thursday 2026-03-05, 12:00 UTC and is moved by hand.
"""

from datetime import UTC, datetime, timedelta

import pytest

from a_core import InvalidStateTransition
from b_domain.entities import User
from b_domain.value_objects import TaskId, TaskStatus
from c_application.dtos.task_dtos import (
    CreateTaskInputDTO,
    GetTaskRequest,
    TaskByUserRequest,
    TaskOutputDTO,
    UpdateTaskInputDTO,
)
from c_application.use_cases import (
    CompleteTaskUseCase,
    CreateTaskUseCase,
    GetTaskUseCase,
    PauseTaskUseCase,
    ReportUseCase,
    StartTaskUseCase,
    UndoPreviewUseCase,
    UndoUseCase,
    UpdateTaskUseCase,
)
from c_application.use_cases.task.report import ReportRequest
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

    started = await StartTaskUseCase(**use_case_context).execute(_by(user, task))
    assert started.task.status == TaskStatus.IN_PROGRESS
    assert started.task.running_since == NOON

    _at(fake_clock, 25)
    paused = await PauseTaskUseCase(**use_case_context).execute(_by(user, task))
    assert paused.task.status == TaskStatus.PAUSED
    assert paused.session_minutes == 25
    assert paused.task.running_since is None

    _at(fake_clock, 60)
    await StartTaskUseCase(**use_case_context).execute(_by(user, task))
    _at(fake_clock, 70)
    done = await CompleteTaskUseCase(**use_case_context).execute(_by(user, task))

    shown = await GetTaskUseCase(**use_case_context).execute(
        GetTaskRequest(task_id_prefix=task.id[:8], user_id=str(user.id))
    )
    assert done.completed_task.status == TaskStatus.DONE
    assert shown.time_spent_minutes == 35  # 25 + 10


async def test_starting_one_task_pauses_the_other(
    use_case_context: UseCaseDeps,
    user: User,
    fake_clock: FakeClock,
    fake_uow_factory: FakeUowFactory,
) -> None:
    first = await _create(use_case_context, user, title="First")
    second = await _create(use_case_context, user, title="Second")
    await StartTaskUseCase(**use_case_context).execute(_by(user, first))

    _at(fake_clock, 15)
    started = await StartTaskUseCase(**use_case_context).execute(_by(user, second))

    assert started.paused_other == "First"
    back = await _task(fake_uow_factory, first)
    assert back is not None and back.status == TaskStatus.PAUSED

    # Undoing the start resumes the first, and throws away the second's session
    assert await _undo(use_case_context, user) == "started"
    first_back = await _task(fake_uow_factory, first)
    second_back = await _task(fake_uow_factory, second)
    assert first_back is not None and first_back.status == TaskStatus.IN_PROGRESS
    assert second_back is not None and second_back.status == TaskStatus.PENDING
    async with fake_uow_factory() as uow:
        running = await uow.time_entries.get_active_for_user(user.id)
    assert running is not None and running.task_id == first_back.id


async def test_undoing_a_pause_runs_the_same_session_again(
    use_case_context: UseCaseDeps,
    user: User,
    fake_clock: FakeClock,
    fake_uow_factory: FakeUowFactory,
) -> None:
    task = await _create(use_case_context, user)
    await StartTaskUseCase(**use_case_context).execute(_by(user, task))
    _at(fake_clock, 20)
    await PauseTaskUseCase(**use_case_context).execute(_by(user, task))

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
        await StartTaskUseCase(**use_case_context).execute(_by(user, after))
    with pytest.raises(InvalidStateTransition, match="not in progress"):
        await PauseTaskUseCase(**use_case_context).execute(_by(user, blocker))
    await StartTaskUseCase(**use_case_context).execute(_by(user, blocker))
    with pytest.raises(InvalidStateTransition, match="already in progress"):
        await StartTaskUseCase(**use_case_context).execute(_by(user, blocker))


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

    await StartTaskUseCase(**use_case_context).execute(_by(user, task))
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
        await StartTaskUseCase(**use_case_context).execute(_by(user, task))
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
