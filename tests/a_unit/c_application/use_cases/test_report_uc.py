"""The report: what the history says happened in a period.

The fake clock says Thursday 2026-03-05, 12:00 UTC; the user is in UTC and
the week starts on Monday.
"""

from datetime import date

import pytest

from a_core import UniqueId
from a_core.exceptions import ValidationException
from b_domain.entities import Context, User
from b_domain.events.task_events import TaskCompletedEvent
from b_domain.value_objects import RecurrenceInterval, TaskId
from b_domain.value_objects.task_history import TaskAction
from c_application.dtos.recurrence_dtos import RecurrenceInputDTO
from c_application.dtos.task_dtos import (
    CreateTaskInputDTO,
    TaskByUserRequest,
    TaskHistoryRequest,
    TaskOutputDTO,
    UpdateTaskInputDTO,
)
from c_application.handlers.task_handlers.create_recurring_task_handler import (
    CreateRecurringTaskHandler,
)
from c_application.use_cases import (
    CompleteTaskUseCase,
    CreateTaskUseCase,
    GetTaskHistoryUseCase,
    ReportUseCase,
    UndoPreviewUseCase,
    UndoUseCase,
    UpdateTaskUseCase,
)
from c_application.use_cases.task.report import ReportOutputDTO, ReportRequest
from c_application.use_cases.task.undo import UndoRequest
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


async def _done(deps: UseCaseDeps, user: User, task: TaskOutputDTO) -> None:
    await CompleteTaskUseCase(**deps).execute(
        TaskByUserRequest(task_id_prefix=task.id[:8], user_id=str(user.id))
    )


async def _report(deps: UseCaseDeps, user: User, **kwargs: object) -> ReportOutputDTO:
    return await ReportUseCase(**deps).execute(
        ReportRequest(user_id=str(user.id), **kwargs)  # type: ignore[arg-type]
    )


async def test_the_week_in_numbers(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    work = Context.create(now=FakeClock().now(), user_id=user.id, name="Work")
    async with fake_uow_factory() as uow:
        await uow.contexts.add(work)
    late = await _create(
        use_case_context, user, title="Late", due_date="2026-03-04 10:00"
    )
    on_time = await _create(
        use_case_context,
        user,
        title="On time",
        due_date="2026-03-10",
        context_id="Work",
        priority=3,  # high
    )
    whenever = await _create(use_case_context, user, title="Whenever")
    for task in (late, on_time, whenever):
        await _done(use_case_context, user, task)
    # Moving the date after the fact does not make it on time
    await UpdateTaskUseCase(**use_case_context).execute(
        UpdateTaskInputDTO(
            task_id_prefix=late.id[:8], user_id=str(user.id), due_date="2026-03-20"
        )
    )

    report = await _report(use_case_context, user)

    assert (report.start, report.end, report.period) == (
        date(2026, 2, 27),
        date(2026, 3, 5),
        "last 7 days",
    )
    assert (report.done, report.created, report.cancelled) == (3, 3, 0)
    assert (report.on_time, report.late, report.no_due) == (1, 1, 1)
    assert [(c.label, c.count) for c in report.by_context] == [("Work", 1), ("none", 2)]
    assert [(c.label, c.count) for c in report.by_priority] == [
        ("high", 1),
        ("medium", 2),
    ]
    assert len(report.days) == 7
    assert (report.days[-1].done, report.days[-1].created) == (3, 3)
    assert report.days[0].done == 0


async def test_an_undone_completion_does_not_count(
    use_case_context: UseCaseDeps, user: User
) -> None:
    task = await _create(use_case_context, user, title="Oops")
    await _done(use_case_context, user, task)
    preview = await UndoPreviewUseCase(**use_case_context).execute(
        UndoRequest(user_id=str(user.id))
    )
    await UndoUseCase(**use_case_context).execute(
        UndoRequest(user_id=str(user.id), entry_id=preview.entry_id)
    )

    assert (await _report(use_case_context, user)).done == 0


@pytest.mark.parametrize(
    ("kwargs", "start", "label"),
    [
        ({"period": "week"}, date(2026, 3, 2), "this week"),  # Monday
        ({"period": "month"}, date(2026, 3, 1), "this month"),
        ({"start": "2026-02-01", "end": "yesterday"}, date(2026, 2, 1), "custom"),
    ],
)
async def test_periods(
    use_case_context: UseCaseDeps,
    user: User,
    kwargs: dict[str, object],
    start: date,
    label: str,
) -> None:
    report = await _report(use_case_context, user, **kwargs)
    assert (report.start, report.period) == (start, label)


async def test_a_period_that_ends_before_it_starts(
    use_case_context: UseCaseDeps, user: User
) -> None:
    with pytest.raises(ValidationException, match="ends before it starts"):
        await _report(use_case_context, user, start="2026-03-05", end="2026-03-01")
    with pytest.raises(ValidationException, match="Unknown period"):
        await _report(use_case_context, user, period="year")


async def test_a_series_carries_its_id_and_has_a_streak(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    gym = await _create(
        use_case_context,
        user,
        title="Gym",
        recurrence=RecurrenceInputDTO(
            frequency=RecurrenceInterval.DAILY, start_date="2026-03-05 07:00"
        ),
    )
    assert gym.series_id == gym.id
    await _done(use_case_context, user, gym)
    # The next occurrence, as the relay's handler makes it
    async with fake_uow_factory() as uow:
        [completion] = [
            e
            for e in await uow.task_history.recent(user.id)
            if e.action == TaskAction.COMPLETED
        ]
        done_gym = await uow.tasks.get_by_id(TaskId.from_string(gym.id))
    assert done_gym is not None
    await CreateRecurringTaskHandler(fake_uow_factory()).handle(
        TaskCompletedEvent(
            id=UniqueId(completion.entry_id),
            occurred_at=completion.occurred_at,
            task_id=done_gym.id,
            user_id=user.id,
            estimated_minutes=30,
            actual_minutes=0,
            energy_level_used=done_gym.required_energy_level,
            task_complexity=done_gym.complexity,
        )
    )

    report = await _report(use_case_context, user)

    [series] = report.series
    assert (series.title, series.done, series.missed, series.streak) == ("Gym", 1, 0, 1)
    assert series.rate == 1.0
    assert series.rule == "Every day."
    assert series.series_id == gym.id
    assert series.task_id != gym.id  # the latest occurrence

    history = await GetTaskHistoryUseCase(**use_case_context).execute(
        TaskHistoryRequest(
            task_id_prefix=series.task_id[:8], user_id=str(user.id), series=True
        )
    )
    assert history.series_size == 2
    assert [e.action for e in history.entries] == ["created", "completed", "created"]


async def test_a_series_with_nothing_in_the_period_is_only_counted(
    use_case_context: UseCaseDeps, user: User
) -> None:
    await _create(
        use_case_context,
        user,
        title="Pay rent",
        recurrence=RecurrenceInputDTO(
            frequency=RecurrenceInterval.MONTHLY, start_date="2026-03-20 09:00"
        ),
    )

    report = await _report(use_case_context, user)

    assert report.series == []
    assert report.quiet_series == 1
