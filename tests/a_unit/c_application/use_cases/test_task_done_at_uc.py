"""Done and forgotten: a task completed at the moment it really was.

The fake clock says Thursday 2026-03-05, 12:00 UTC; the user is in UTC.
"""

from datetime import UTC, datetime, timedelta

import pytest

from a_core import UniqueId
from a_core.exceptions import InvalidValueError, ValidationException
from b_domain.entities import User
from b_domain.events.task_events import TaskCompletedEvent
from b_domain.ports.repositories.filters import TaskFilter
from b_domain.value_objects import RecurrenceInterval, TaskId
from b_domain.value_objects.task_history import TaskAction
from c_application.dtos.recurrence_dtos import RecurrenceInputDTO
from c_application.dtos.task_dtos import (
    CreateTaskInputDTO,
    GetTaskRequest,
    TaskByUserRequest,
    TaskOutputDTO,
)
from c_application.handlers.task_handlers.create_recurring_task_handler import (
    CreateRecurringTaskHandler,
)
from c_application.use_cases import (
    CompleteTaskUseCase,
    CreateTaskUseCase,
    GetTaskUseCase,
    ReportUseCase,
    StartTaskUseCase,
)
from c_application.use_cases.task.report import ReportRequest
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


async def _done_at(deps: UseCaseDeps, user: User, task: TaskOutputDTO, at: str):  # type: ignore[no-untyped-def]
    return await CompleteTaskUseCase(**deps).execute(
        TaskByUserRequest(
            task_id_prefix=task.id[:8], user_id=str(user.id), completed_at=at
        )
    )


async def test_done_at_a_moment_typed(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    task = await _create(use_case_context, user)

    done = await _done_at(use_case_context, user, task, "yesterday 21:00")

    moment = datetime(2026, 3, 4, 21, 0, tzinfo=UTC)
    assert done.completed_task.completed_at == moment
    async with fake_uow_factory() as uow:
        [entry] = [
            e
            for e in await uow.task_history.recent(user.id)
            if e.action == TaskAction.COMPLETED
        ]
    assert entry.occurred_at == moment
    # The report counts it on its own day
    report = await ReportUseCase(**use_case_context).execute(
        ReportRequest(user_id=str(user.id))
    )
    assert [d.done for d in report.days][-2:] == [1, 0]


async def test_a_time_alone_is_today(use_case_context: UseCaseDeps, user: User) -> None:
    task = await _create(use_case_context, user)
    done = await _done_at(use_case_context, user, task, "9:15")
    assert done.completed_task.completed_at == datetime(2026, 3, 5, 9, 15, tzinfo=UTC)


@pytest.mark.parametrize(
    ("typed", "error", "match"),
    [
        ("tomorrow 09:00", ValidationException, "in the future"),
        ("12:01", ValidationException, "in the future"),
        ("yesterday", ValidationException, "needs a time of day"),
        ("last night", InvalidValueError, "Invalid date"),
    ],
)
async def test_moments_refused(
    use_case_context: UseCaseDeps,
    user: User,
    typed: str,
    error: type[Exception],
    match: str,
) -> None:
    task = await _create(use_case_context, user)
    with pytest.raises(error, match=match):
        await _done_at(use_case_context, user, task, typed)


async def test_a_running_timer_stops_at_the_moment(
    use_case_context: UseCaseDeps, user: User, fake_clock: FakeClock
) -> None:
    task = await _create(use_case_context, user)
    await StartTaskUseCase(**use_case_context).execute(
        TaskByUserRequest(task_id_prefix=task.id[:8], user_id=str(user.id))
    )
    fake_clock.set_time(NOON + timedelta(hours=2))

    # Before the timer started: its session would end before it began
    with pytest.raises(ValidationException, match="timer that started after"):
        await _done_at(use_case_context, user, task, "11:00")

    await _done_at(use_case_context, user, task, "12:30")
    shown = await GetTaskUseCase(**use_case_context).execute(
        GetTaskRequest(task_id_prefix=task.id[:8], user_id=str(user.id))
    )
    assert shown.time_spent_minutes == 30


async def test_the_next_occurrence_follows_the_moment(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    """Yesterday's 08:00 done last night: the next one is today's, though
    today's 08:00 has passed."""
    walk = await _create(
        use_case_context,
        user,
        title="Walk",
        recurrence=RecurrenceInputDTO(
            frequency=RecurrenceInterval.DAILY, start_date="2026-03-04 08:00"
        ),
    )
    await _done_at(use_case_context, user, walk, "yesterday 21:00")
    async with fake_uow_factory() as uow:
        [entry] = [
            e
            for e in await uow.task_history.recent(user.id)
            if e.action == TaskAction.COMPLETED
        ]
        closed = await uow.tasks.get_by_id(TaskId.from_string(walk.id))
    assert closed is not None
    await CreateRecurringTaskHandler(fake_uow_factory()).handle(
        TaskCompletedEvent(
            id=UniqueId(entry.entry_id),
            occurred_at=entry.occurred_at,
            task_id=closed.id,
            user_id=user.id,
            estimated_minutes=30,
            actual_minutes=0,
            energy_level_used=closed.required_energy_level,
            task_complexity=closed.complexity,
        )
    )

    async with fake_uow_factory() as uow:
        series = await uow.tasks.list(TaskFilter(user_id=user.id, in_series=True))
    assert sorted(
        t.due_date.value.replace(tzinfo=None) for t in series if t.due_date
    ) == [datetime(2026, 3, 4, 8, 0), datetime(2026, 3, 5, 8, 0)]
