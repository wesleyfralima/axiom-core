"""Due dates as typed (default due time, day words), projected occurrences
and what an edit can change.

The fake clock says 2026-03-05 12:00 UTC (a Thursday); the user is in UTC.
"""

from datetime import datetime

import pytest

from a_core.exceptions import InvalidValueError, ValidationException
from b_domain.entities import Context, User
from b_domain.value_objects import RecurrenceInterval, TaskStatus
from b_domain.value_objects.enums import EnergyLevel
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


async def test_the_list_filters_one_day(
    use_case_context: UseCaseDeps, user: User
) -> None:
    """--due today: from its first minute to its last, no more."""
    for title, due in (
        ("Yesterday", "yesterday 23:59"),
        ("Early today", "today 00:00"),
        ("Late today", "today 23:59"),
        ("Tomorrow", "tomorrow 00:00"),
    ):
        await CreateTaskUseCase(**use_case_context).execute(
            CreateTaskInputDTO(user_id=str(user.id), title=title, due_date=due)
        )
    await _create(use_case_context, user)  # no date

    today = await _list(use_case_context, user, due_on="today")
    by_date = await _list(use_case_context, user, due_on="2026-03-06 15:00")

    assert sorted(t.title for t in today.tasks) == ["Early today", "Late today"]
    assert [t.title for t in by_date.tasks] == ["Tomorrow"]
    with pytest.raises(ValidationException, match="not both"):
        await _list(use_case_context, user, due_on="today", due_before="tomorrow")


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


# ---------------------------------------------------------------- edit


async def _edit(
    deps: UseCaseDeps, user: User, prefix: str, **kwargs: object
) -> TaskOutputDTO:
    return await UpdateTaskUseCase(**deps).execute(
        UpdateTaskInputDTO(task_id_prefix=prefix, user_id=str(user.id), **kwargs)  # type: ignore[arg-type]
    )


async def test_editing_removes_the_due_date(
    use_case_context: UseCaseDeps, user: User
) -> None:
    created = await _create(use_case_context, user, due_date="tomorrow")

    edited = await _edit(use_case_context, user, created.id[:8], remove_due_date=True)

    assert edited.due_date is None


async def test_editing_changes_energy_and_context(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    work = Context.create(now=datetime(2026, 3, 5), user_id=user.id, name="Work")
    async with fake_uow_factory() as uow:
        await uow.contexts.add(work)
    created = await _create(use_case_context, user)
    prefix = created.id[:8]

    edited = await _edit(
        use_case_context, user, prefix, energy_level="high", context_id="work"
    )
    assert edited.required_energy_level == EnergyLevel.HIGH.value
    assert edited.context_name == "Work"

    cleared = await _edit(use_case_context, user, prefix, remove_context=True)
    assert cleared.context_id is None


async def test_editing_refuses_contradictions(
    use_case_context: UseCaseDeps, user: User
) -> None:
    created = await _create(use_case_context, user, due_date="tomorrow")

    with pytest.raises(ValidationException, match="not both"):
        await _edit(
            use_case_context,
            user,
            created.id[:8],
            due_date="today",
            remove_due_date=True,
        )


# ---------------------------------------------------------------- recurrence


def _weekly(*days: int, **kwargs: object) -> RecurrenceInputDTO:
    return RecurrenceInputDTO(
        frequency=RecurrenceInterval.WEEKLY,
        by_week_days=list(days),
        **kwargs,  # type: ignore[arg-type]
    )


async def test_a_new_rule_keeps_the_due_date_and_leads_the_next_ones(
    use_case_context: UseCaseDeps, user: User
) -> None:
    # Due Monday the 9th at 07:00, every Monday
    created = await _create(
        use_case_context, user, recurrence=_weekly(0, start_date="2026-03-09 07:00")
    )

    edited = await _edit(
        use_case_context, user, created.id[:8], recurrence=_weekly(1, 3)
    )

    assert edited.due_date == datetime(2026, 3, 9, 7, 0)  # untouched
    assert edited.recurrence_display is not None
    assert "Tuesdays and Thursdays" in edited.recurrence_display
    # days_ahead 7 → up to the 12th: Tue 10, Thu 12
    assert edited.next_occurrences == [
        datetime(2026, 3, 10, 7, 0),
        datetime(2026, 3, 12, 7, 0),
    ]


async def test_the_preview_shows_at_least_the_next_one(
    use_case_context: UseCaseDeps, user: User
) -> None:
    created = await _create(use_case_context, user, due_date="2026-03-09 07:00")

    edited = await _edit(
        use_case_context,
        user,
        created.id[:8],
        recurrence=RecurrenceInputDTO(frequency=RecurrenceInterval.MONTHLY),
    )

    assert edited.next_occurrences == [datetime(2026, 4, 9, 7, 0)]


async def test_the_preview_stops_at_ten_even_hourly(
    use_case_context: UseCaseDeps, user: User
) -> None:
    created = await _create(use_case_context, user, due_date="2026-03-09 07:00")

    edited = await _edit(
        use_case_context,
        user,
        created.id[:8],
        recurrence=RecurrenceInputDTO(frequency=RecurrenceInterval.HOURLY),
    )

    assert len(edited.next_occurrences) == 10
    assert edited.next_occurrences[0] == datetime(2026, 3, 9, 8, 0)


async def test_stop_repeating_and_start_repeating(
    use_case_context: UseCaseDeps, user: User
) -> None:
    created = await _create(use_case_context, user, recurrence=_daily("tomorrow 07:00"))
    prefix = created.id[:8]

    one_off = await _edit(use_case_context, user, prefix, remove_recurrence=True)
    assert one_off.recurrence is None
    assert one_off.next_occurrences == []
    assert one_off.due_date == datetime(2026, 3, 6, 7, 0)

    plain = await _create(use_case_context, user)
    repeating = await _edit(use_case_context, user, plain.id[:8], recurrence=_weekly(4))
    # No due date: the rule's first occurrence becomes it (default due time)
    assert repeating.due_date == datetime(2026, 3, 6, 23, 59)  # Friday


async def test_the_rule_comes_back_as_fields(
    use_case_context: UseCaseDeps, user: User
) -> None:
    created = await _create(
        use_case_context,
        user,
        recurrence=_weekly(0, 2, start_date="2026-03-09 07:00", count=4, interval=2),
    )

    rule = created.recurrence
    assert rule is not None
    assert (rule.frequency, rule.interval, rule.count, rule.by_week_days) == (
        RecurrenceInterval.WEEKLY,
        2,
        4,
        [0, 2],
    )


async def test_count_is_what_is_left(use_case_context: UseCaseDeps, user: User) -> None:
    created = await _create(
        use_case_context, user, recurrence=_daily("tomorrow 07:00", count=3)
    )
    # This one and two more
    assert created.next_occurrences == [
        datetime(2026, 3, 7, 7, 0),
        datetime(2026, 3, 8, 7, 0),
    ]


async def test_the_last_day_of_the_week_follows_week_start(
    use_case_context: UseCaseDeps, user: User
) -> None:
    last_day = RecurrenceInputDTO(
        frequency=RecurrenceInterval.WEEKLY,
        by_set_pos=-1,
        start_date="2026-03-05 07:00",
    )

    from_monday = await _create(use_case_context, user, recurrence=last_day)
    assert from_monday.recurrence_display is not None
    assert "last day (Sunday)" in from_monday.recurrence_display

    user.preferences = user.preferences.update(week_start="sunday")
    from_sunday = await _create(use_case_context, user, recurrence=last_day)
    assert from_sunday.recurrence_display is not None
    assert "last day (Saturday)" in from_sunday.recurrence_display
    assert from_sunday.due_date == datetime(2026, 3, 7, 7, 0)
