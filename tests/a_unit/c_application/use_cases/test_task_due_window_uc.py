"""The due date as a block (due + estimate), or a hard deadline (strict):
what is late in the list, in the report, and which occurrence comes next.

The fake clock is moved to Thursday 2026-03-05 by hand; the user is in UTC.
"""

from datetime import UTC, datetime

import pytest

from a_core import UniqueId
from b_domain.entities import User
from b_domain.events.task_events import TaskCancelledEvent
from b_domain.ports.repositories.filters import TaskFilter
from b_domain.value_objects import RecurrenceInterval, TaskId
from c_application.dtos.recurrence_dtos import RecurrenceInputDTO
from c_application.dtos.task_dtos import (
    CancelTaskInputDTO,
    CreateTaskInputDTO,
    GetTaskRequest,
    ListTasksRequest,
    TaskByUserRequest,
    TaskHistoryRequest,
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
    GetTaskHistoryUseCase,
    GetTaskUseCase,
    ListTasksUseCase,
    ReportUseCase,
    UndoPreviewUseCase,
    UndoUseCase,
    UpdateTaskUseCase,
)
from c_application.use_cases.task.report import ReportRequest
from c_application.use_cases.task.undo import UndoRequest
from tests.conftest import FakeClock, FakeUowFactory, UseCaseDeps

pytestmark = [pytest.mark.asyncio, pytest.mark.uc]


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 3, 5, hour, minute, tzinfo=UTC)


@pytest.fixture
async def user(fake_uow_factory: FakeUowFactory, fake_clock: FakeClock) -> User:
    created = User.create(username="wesley", email="wesley@test.com")
    await fake_uow_factory().users.add(created)
    fake_clock.set_time(_at(7))
    return created


async def _create(deps: UseCaseDeps, user: User, **kwargs: object) -> TaskOutputDTO:
    return await CreateTaskUseCase(**deps).execute(
        CreateTaskInputDTO(
            user_id=str(user.id),
            **{"title": "Write the report", "due_date": "today 08:00", **kwargs},  # type: ignore[arg-type]
        )
    )


async def _show(deps: UseCaseDeps, user: User, task: TaskOutputDTO) -> TaskOutputDTO:
    return await GetTaskUseCase(**deps).execute(
        GetTaskRequest(task_id_prefix=task.id[:8], user_id=str(user.id))
    )


async def test_done_within_its_block_is_on_time(
    use_case_context: UseCaseDeps, user: User, fake_clock: FakeClock
) -> None:
    """Due at 08:00, lasting 2 hours, done at 09:45: on time."""
    task = await _create(use_case_context, user, estimated_minutes=120)
    fake_clock.set_time(_at(9, 45))

    shown = await _show(use_case_context, user, task)
    assert (shown.is_overdue, shown.strict_due) == (False, False)
    assert shown.deadline == _at(10)

    await CompleteTaskUseCase(**use_case_context).execute(
        TaskByUserRequest(task_id_prefix=task.id[:8], user_id=str(user.id))
    )
    report = await ReportUseCase(**use_case_context).execute(
        ReportRequest(user_id=str(user.id))
    )
    assert (report.on_time, report.late) == (1, 0)


async def test_after_its_block_it_is_late(
    use_case_context: UseCaseDeps, user: User, fake_clock: FakeClock
) -> None:
    task = await _create(use_case_context, user, estimated_minutes=120)
    fake_clock.set_time(_at(10, 1))
    assert (await _show(use_case_context, user, task)).is_overdue


async def test_a_strict_due_date_is_late_right_after_it(
    use_case_context: UseCaseDeps, user: User, fake_clock: FakeClock
) -> None:
    task = await _create(use_case_context, user, estimated_minutes=120, strict_due=True)
    fake_clock.set_time(_at(9, 45))

    shown = await _show(use_case_context, user, task)
    assert (shown.is_overdue, shown.strict_due, shown.deadline) == (
        True,
        True,
        _at(8),
    )

    await CompleteTaskUseCase(**use_case_context).execute(
        TaskByUserRequest(task_id_prefix=task.id[:8], user_id=str(user.id))
    )
    report = await ReportUseCase(**use_case_context).execute(
        ReportRequest(user_id=str(user.id))
    )
    assert (report.on_time, report.late) == (0, 1)


async def test_strict_is_edited_recorded_and_undone(
    use_case_context: UseCaseDeps, user: User
) -> None:
    task = await _create(use_case_context, user)

    edited = await UpdateTaskUseCase(**use_case_context).execute(
        UpdateTaskInputDTO(
            task_id_prefix=task.id[:8], user_id=str(user.id), strict_due=True
        )
    )
    assert edited.strict_due is True
    history = await GetTaskHistoryUseCase(**use_case_context).execute(
        TaskHistoryRequest(task_id_prefix=task.id[:8], user_id=str(user.id))
    )
    [edit] = [e for e in history.entries if e.action == "edited"]
    assert [(c.field, c.before, c.after) for c in edit.changes] == [
        ("strict", None, "yes")
    ]

    preview = await UndoPreviewUseCase(**use_case_context).execute(
        UndoRequest(user_id=str(user.id))
    )
    await UndoUseCase(**use_case_context).execute(
        UndoRequest(user_id=str(user.id), entry_id=preview.entry_id)
    )
    assert (await _show(use_case_context, user, task)).strict_due is False


async def test_a_subtask_due_with_its_parent_is_late_with_it(
    use_case_context: UseCaseDeps, user: User, fake_clock: FakeClock
) -> None:
    parent = await _create(use_case_context, user, estimated_minutes=120)
    sub = await _create(
        use_case_context,
        user,
        title="Check the numbers",
        estimated_minutes=15,
        parent_id=parent.id[:8],
    )
    fake_clock.set_time(_at(9, 45))

    listed = await ListTasksUseCase(**use_case_context).execute(
        ListTasksRequest(user_id=str(user.id))
    )
    assert {t.title: t.is_overdue for t in listed.tasks} == {
        "Write the report": False,
        "Check the numbers": False,
    }
    assert (await _show(use_case_context, user, sub)).deadline == _at(10)


async def _occurrence_dues(
    fake_uow_factory: FakeUowFactory, user: User
) -> list[datetime]:
    async with fake_uow_factory() as uow:
        tasks = await uow.tasks.list(TaskFilter(user_id=user.id, in_series=True))
    return sorted(t.due_date.value.replace(tzinfo=None) for t in tasks if t.due_date)


@pytest.mark.parametrize(
    ("strict", "next_due"),
    [
        # Today's 08:00 lasting 2 hours is still to do at 09:00
        (False, datetime(2026, 3, 5, 8, 0)),
        # A hard 08:00 deadline has passed: tomorrow's
        (True, datetime(2026, 3, 6, 8, 0)),
    ],
)
async def test_a_skip_makes_the_next_occurrence_still_on_time(
    use_case_context: UseCaseDeps,
    user: User,
    fake_clock: FakeClock,
    fake_uow_factory: FakeUowFactory,
    strict: bool,
    next_due: datetime,
) -> None:
    """Yesterday's not done, skipped today at 09:00 so today's shows up."""
    walk = await _create(
        use_case_context,
        user,
        title="Walk",
        due_date=None,
        estimated_minutes=120,
        strict_due=strict,
        recurrence=RecurrenceInputDTO(
            frequency=RecurrenceInterval.DAILY, start_date="2026-03-04 08:00"
        ),
    )
    fake_clock.set_time(_at(9))
    await CancelTaskUseCase(**use_case_context).execute(
        CancelTaskInputDTO(task_id_prefix=walk.id[:8], user_id=str(user.id))
    )
    async with fake_uow_factory() as uow:
        last = (await uow.task_history.recent(user.id))[0]
    await CreateRecurringTaskHandler(fake_uow_factory()).handle(
        TaskCancelledEvent(
            id=UniqueId(last.entry_id),
            occurred_at=last.occurred_at,
            task_id=TaskId.from_string(walk.id),
            user_id=user.id,
        )
    )

    assert await _occurrence_dues(fake_uow_factory, user) == [
        datetime(2026, 3, 4, 8, 0),
        next_due,
    ]
