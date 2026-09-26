"""Due dates as typed (default due time, day words) and projected occurrences.

The fake clock says 2026-03-05 12:00 UTC (a Thursday); the user is in UTC.
"""

from datetime import datetime

import pytest

from a_core.exceptions import InvalidValueError
from b_domain.entities import User
from b_domain.value_objects import RecurrenceInterval, TaskStatus
from c_application.dtos.recurrence_dtos import RecurrenceInputDTO
from c_application.dtos.task_dtos import (
    CreateTaskInputDTO,
    GetTaskRequest,
    ListTasksRequest,
    TaskListOutputDTO,
    TaskOutputDTO,
    UpdateTaskInputDTO,
)
from c_application.use_cases import (
    CreateTaskUseCase,
    GetTaskUseCase,
    ListTasksUseCase,
    UpdateTaskUseCase,
)
from tests.conftest import FakeUowFactory, UseCaseDeps

pytestmark = [pytest.mark.asyncio, pytest.mark.uc]


@pytest.fixture
async def user(fake_uow_factory: FakeUowFactory) -> User:
    created = User.create(username="wesley", email="wesley@test.com")
    await fake_uow_factory().users.add(created)
    return created


async def _create(deps: UseCaseDeps, user: User, **kwargs: object) -> TaskOutputDTO:
    return await CreateTaskUseCase(**deps).execute(
        CreateTaskInputDTO(user_id=str(user.id), title="Task", **kwargs)  # type: ignore[arg-type]
    )


async def _list(deps: UseCaseDeps, user: User, **kwargs: object) -> TaskListOutputDTO:
    return await ListTasksUseCase(**deps).execute(
        ListTasksRequest(user_id=str(user.id), **kwargs)  # type: ignore[arg-type]
    )


def _daily(start: str | None = None, **kwargs: object) -> RecurrenceInputDTO:
    return RecurrenceInputDTO(
        frequency=RecurrenceInterval.DAILY,
        start_date=start,
        **kwargs,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------- due dates


async def test_a_date_without_time_gets_the_default_due_time(
    use_case_context: UseCaseDeps, user: User
) -> None:
    created = await _create(use_case_context, user, due_date="2026-03-10")
    assert created.due_date == datetime(2026, 3, 10, 23, 59)


async def test_the_default_due_time_is_a_preference(
    use_case_context: UseCaseDeps, user: User
) -> None:
    user.preferences = user.preferences.update(default_due_time="09:00")

    created = await _create(use_case_context, user, due_date="tomorrow")

    assert created.due_date == datetime(2026, 3, 6, 9, 0)


async def test_day_words_with_a_time(use_case_context: UseCaseDeps, user: User) -> None:
    created = await _create(use_case_context, user, due_date="today 18:30")
    assert created.due_date == datetime(2026, 3, 5, 18, 30)


async def test_an_unknown_expression_is_refused(
    use_case_context: UseCaseDeps, user: User
) -> None:
    with pytest.raises(InvalidValueError, match="Invalid date"):
        await _create(use_case_context, user, due_date="someday soon")


async def test_editing_the_due_date_takes_words_too(
    use_case_context: UseCaseDeps, user: User
) -> None:
    created = await _create(use_case_context, user, due_date="2026-03-10 08:00")

    edited = await UpdateTaskUseCase(**use_case_context).execute(
        UpdateTaskInputDTO(
            task_id_prefix=created.id[:8], user_id=str(user.id), due_date="tomorrow"
        )
    )

    assert edited.due_date == datetime(2026, 3, 6, 23, 59)


async def test_a_recurrence_without_start_begins_today_at_the_default_time(
    use_case_context: UseCaseDeps, user: User
) -> None:
    created = await _create(use_case_context, user, recurrence=_daily())
    assert created.due_date == datetime(2026, 3, 5, 23, 59)


async def test_a_recurrence_start_word_and_until_date(
    use_case_context: UseCaseDeps, user: User
) -> None:
    created = await _create(
        use_case_context,
        user,
        recurrence=_daily("tomorrow 07:00", end_date="2026-03-08"),
    )

    assert created.due_date == datetime(2026, 3, 6, 7, 0)
    # "until" a date: that whole day counts (the 8th at 07:00 is in)
    assert created.next_occurrences == [
        datetime(2026, 3, 7, 7, 0),
        datetime(2026, 3, 8, 7, 0),
    ]


# ---------------------------------------------------------------- projection


async def test_the_list_projects_recurring_tasks_days_ahead(
    use_case_context: UseCaseDeps, user: User
) -> None:
    await _create(use_case_context, user, recurrence=_daily("tomorrow 07:00"))
    await _create(use_case_context, user, due_date="tomorrow")

    listed = await _list(use_case_context, user)

    assert len(listed.tasks) == 2
    # Default: 7 days ahead → the 7th to the 12th (the 6th is the real task)
    assert [p.due_date for p in listed.projected] == [
        datetime(2026, 3, day, 7, 0) for day in range(7, 13)
    ]
    assert all(
        p.is_projected and p.status == TaskStatus.PENDING for p in listed.projected
    )


async def test_ahead_takes_days_or_a_date(
    use_case_context: UseCaseDeps, user: User
) -> None:
    await _create(use_case_context, user, recurrence=_daily("tomorrow 07:00"))

    assert len((await _list(use_case_context, user, ahead=2)).projected) == 1
    assert len((await _list(use_case_context, user, ahead=0)).projected) == 0
    by_date = await _list(use_case_context, user, ahead="2026-03-20")
    assert by_date.projected[-1].due_date == datetime(2026, 3, 20, 7, 0)


async def test_the_days_ahead_preference_is_the_default(
    use_case_context: UseCaseDeps, user: User
) -> None:
    user.preferences = user.preferences.update(days_ahead=3)
    await _create(use_case_context, user, recurrence=_daily("tomorrow 07:00"))

    listed = await _list(use_case_context, user)

    assert [p.due_date.day for p in listed.projected if p.due_date] == [7, 8]


async def test_hourly_and_closed_tasks_are_not_projected(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    await _create(
        use_case_context,
        user,
        recurrence=RecurrenceInputDTO(
            frequency=RecurrenceInterval.HOURLY, start_date="tomorrow 07:00"
        ),
    )
    daily = await _create(use_case_context, user, recurrence=_daily("tomorrow 07:00"))
    async with fake_uow_factory() as uow:
        [task] = [t for t in uow.tasks.tasks.values() if str(t.id) == daily.id]
        task.status = TaskStatus.CANCELLED

    assert (await _list(use_case_context, user)).projected == []


async def test_show_projects_the_occurrences_ahead(
    use_case_context: UseCaseDeps, user: User
) -> None:
    created = await _create(use_case_context, user, recurrence=_daily("tomorrow 07:00"))
    one_off = await _create(use_case_context, user, due_date="tomorrow")

    shown = await GetTaskUseCase(**use_case_context).execute(
        GetTaskRequest(task_id_prefix=created.id[:8], user_id=str(user.id), ahead=3)
    )
    assert shown.next_occurrences == [
        datetime(2026, 3, 7, 7, 0),
        datetime(2026, 3, 8, 7, 0),
    ]

    plain = await GetTaskUseCase(**use_case_context).execute(
        GetTaskRequest(task_id_prefix=one_off.id[:8], user_id=str(user.id), ahead=30)
    )
    assert plain.next_occurrences == []
