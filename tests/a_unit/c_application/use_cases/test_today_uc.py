"""The day at a glance: late, due today, done today and the next few.

The fake clock is moved to Thursday 2026-03-05, 07:00 by hand; the user is
in UTC unless a test says otherwise.
"""

from datetime import UTC, date, datetime

import pytest

from a_core import UniqueId
from b_domain.entities import User
from b_domain.events.task_events import TaskCompletedEvent
from b_domain.value_objects import RecurrenceInterval, TaskId
from b_domain.value_objects.task_history import TaskAction
from c_application.dtos.recurrence_dtos import RecurrenceInputDTO
from c_application.dtos.task_dtos import (
    AddSubtasksInputDTO,
    CreateTaskInputDTO,
    TaskByUserRequest,
    TaskOutputDTO,
)
from c_application.handlers.task_handlers.create_recurring_task_handler import (
    CreateRecurringTaskHandler,
)
from c_application.use_cases import (
    AddSubtasksUseCase,
    CompleteTaskUseCase,
    CreateContextUseCase,
    CreateTaskUseCase,
    TodayUseCase,
)
from c_application.use_cases.context.create import CreateContextInputDTO
from c_application.use_cases.task.today import TodayOutputDTO, TodayRequest
from tests.conftest import FakeClock, FakeUowFactory, UseCaseDeps

pytestmark = [pytest.mark.asyncio, pytest.mark.uc]


def _at(hour: int, minute: int = 0, day: int = 5) -> datetime:
    return datetime(2026, 3, day, hour, minute, tzinfo=UTC)


@pytest.fixture
async def user(fake_uow_factory: FakeUowFactory, fake_clock: FakeClock) -> User:
    created = User.create(username="wesley", email="wesley@test.com")
    await fake_uow_factory().users.add(created)
    fake_clock.set_time(_at(7))
    return created


async def _create(
    deps: UseCaseDeps, user: User, title: str, **kwargs: object
) -> TaskOutputDTO:
    return await CreateTaskUseCase(**deps).execute(
        CreateTaskInputDTO(user_id=str(user.id), title=title, **kwargs)  # type: ignore[arg-type]
    )


async def _done(
    deps: UseCaseDeps, user: User, task: TaskOutputDTO, at: str | None = None
) -> None:
    await CompleteTaskUseCase(**deps).execute(
        TaskByUserRequest(
            task_id_prefix=task.id[:8], user_id=str(user.id), completed_at=at
        )
    )


async def _today(deps: UseCaseDeps, user: User, **kwargs: object) -> TodayOutputDTO:
    return await TodayUseCase(**deps).execute(
        TodayRequest(user_id=str(user.id), **kwargs)  # type: ignore[arg-type]
    )


def _titles(tasks: list[TaskOutputDTO]) -> list[str]:
    return [t.title for t in tasks]


async def test_the_day_in_its_four_lists(
    use_case_context: UseCaseDeps, user: User
) -> None:
    for title, due in [
        ("Ten days", "2026-03-15 09:00"),
        ("Tonight", "today 23:59"),
        ("Yesterday's bill", "yesterday 18:00"),
        ("Tomorrow", "tomorrow 09:00"),
        ("Early", "today 05:30"),  # lasts an hour: late at 06:30
        ("Monday", "2026-03-09 09:00"),
        ("Saturday", "2026-03-07 09:00"),
        ("Soon", "today 08:00"),
    ]:
        await _create(use_case_context, user, title, due_date=due)
    await _create(use_case_context, user, "No date")

    day = await _today(use_case_context, user)

    assert day.day == date(2026, 3, 5)
    assert _titles(day.overdue) == ["Yesterday's bill", "Early"]
    assert all(t.is_overdue for t in day.overdue)
    assert _titles(day.today) == ["Soon", "Tonight"]
    assert _titles(day.next) == ["Tomorrow", "Saturday", "Monday"]
    assert day.done == []
    assert day.context is None


async def test_how_many_come_next(use_case_context: UseCaseDeps, user: User) -> None:
    for n in range(1, 6):
        await _create(
            use_case_context, user, f"Day {n}", due_date=f"2026-03-{5 + n:02d}"
        )

    assert _titles((await _today(use_case_context, user, next_count=1)).next) == [
        "Day 1"
    ]
    assert len((await _today(use_case_context, user, next_count=5)).next) == 5


async def test_a_task_in_its_block_is_today_not_late(
    use_case_context: UseCaseDeps, user: User, fake_clock: FakeClock
) -> None:
    await _create(
        use_case_context, user, "Long", due_date="today 06:00", estimated_minutes=120
    )
    assert _titles((await _today(use_case_context, user)).today) == ["Long"]

    fake_clock.set_time(_at(8, 1))
    assert _titles((await _today(use_case_context, user)).overdue) == ["Long"]


async def test_done_today_in_the_order_it_was(
    use_case_context: UseCaseDeps, user: User, fake_clock: FakeClock
) -> None:
    second = await _create(use_case_context, user, "Second", due_date="today 23:00")
    first = await _create(use_case_context, user, "First")
    yesterday = await _create(use_case_context, user, "Last night")
    await _done(use_case_context, user, second)  # 07:00
    await _done(use_case_context, user, first, at="06:30")
    await _done(use_case_context, user, yesterday, at="yesterday 21:00")

    day = await _today(use_case_context, user)

    assert _titles(day.done) == ["First", "Second"]
    assert day.today == []


async def test_a_habit_done_today_shows_its_next_occurrence(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    gym = await _create(
        use_case_context,
        user,
        "Gym",
        recurrence=RecurrenceInputDTO(
            frequency=RecurrenceInterval.DAILY, start_date="today 06:30"
        ),
    )
    await _done(use_case_context, user, gym)
    # The event's handler, as the outbox relay runs it
    async with fake_uow_factory() as uow:
        [entry] = [
            e
            for e in await uow.task_history.recent(user.id)
            if e.action == TaskAction.COMPLETED
        ]
        closed = await uow.tasks.get_by_id(TaskId.from_string(gym.id))
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

    day = await _today(use_case_context, user)

    assert _titles(day.done) == ["Gym"]
    assert _titles(day.next) == ["Gym"]
    assert day.next[0].due_date == datetime(2026, 3, 6, 6, 30)


async def test_every_context_unless_one_is_asked_for(
    use_case_context: UseCaseDeps, user: User
) -> None:
    for name in ("Work", "Home"):
        await CreateContextUseCase(**use_case_context).execute(
            CreateContextInputDTO(user_id=str(user.id), name=name)
        )
    await _create(
        use_case_context, user, "Report", due_date="today 18:00", context_id="Work"
    )
    await _create(
        use_case_context, user, "Bill", due_date="yesterday 18:00", context_id="Home"
    )

    day = await _today(use_case_context, user)
    assert _titles(day.overdue + day.today) == ["Bill", "Report"]
    assert day.overdue[0].context_name == "Home"

    work = await _today(use_case_context, user, context_id="work")
    assert _titles(work.overdue + work.today) == ["Report"]
    assert work.context is not None and work.context.name == "Work"


async def test_subtasks_today_but_not_the_ones_due_with_their_parent_next(
    use_case_context: UseCaseDeps, user: User
) -> None:
    today = await _create(use_case_context, user, "Groceries", due_date="today 18:00")
    trip = await _create(use_case_context, user, "Trip", due_date="2026-03-20 08:00")
    for parent, titles, extra in [
        (today, ["Milk"], {}),
        (trip, ["Pack"], {}),  # due with the trip
        (trip, ["Book the car"], {"due_date": "2026-03-10 18:00"}),
    ]:
        await AddSubtasksUseCase(**use_case_context).execute(
            AddSubtasksInputDTO(
                user_id=str(user.id),
                parent_id=parent.id[:8],
                titles=titles,
                **extra,  # type: ignore[arg-type]
            )
        )

    day = await _today(use_case_context, user)

    assert _titles(day.today) == ["Groceries", "Milk"]
    assert day.today[1].parent_title == "Groceries"
    assert _titles(day.next) == ["Book the car", "Trip"]


async def test_today_is_where_the_user_is(
    use_case_context: UseCaseDeps, user: User, fake_clock: FakeClock
) -> None:
    """At 01:00 UTC on Friday it is still Thursday 22:00 in São Paulo."""
    user.preferences = user.preferences.update(timezone="America/Sao_Paulo")
    await _create(use_case_context, user, "Tonight", due_date="today 23:00")
    await _create(use_case_context, user, "Tomorrow", due_date="tomorrow 09:00")
    fake_clock.set_time(_at(1, day=6))

    day = await _today(use_case_context, user)

    assert day.day == date(2026, 3, 5)
    assert _titles(day.today) == ["Tonight"]
    assert _titles(day.next) == ["Tomorrow"]
