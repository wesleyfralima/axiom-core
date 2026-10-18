"""Subtasks on their own days (product Backlog 06, Part 1): a subtask's
estimate counts on the day it is due, its parent only its own part — its
estimate minus every subtask's (open, done or cancelled), never below zero;
every subtask cancelled, the extra it planned or the last one cancelled.

The owner's trip: "Organize the trip", due in two months; rent a car (in a
week, 30m), book the hotel (in 3 days, 1h), buy what is needed (in two
weeks, 3h). The fake clock is at 07:00 on 2026-03-05, the user in UTC, the
day 13h30 long (810 minutes).
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
    CancelTaskInputDTO,
    CreateTaskInputDTO,
    GetTaskRequest,
    TaskByUserRequest,
    TaskOutputDTO,
    UpdateTaskInputDTO,
)
from c_application.handlers.task_handlers.create_recurring_task_handler import (
    CreateRecurringTaskHandler,
)
from c_application.use_cases import (
    AddSubtasksUseCase,
    CancelTaskUseCase,
    CompleteTaskUseCase,
    CreateTaskUseCase,
    DeleteTaskUseCase,
    GetTaskUseCase,
    ReopenTaskUseCase,
    TodayUseCase,
    UpdateTaskUseCase,
    WrapUseCase,
)
from c_application.use_cases.task.capacity import day_load
from c_application.use_cases.task.delete import DeleteTaskInputDTO
from c_application.use_cases.task.today import TodayRequest
from c_application.use_cases.task.wrap import WrapRequest
from tests.conftest import FakeClock, FakeUowFactory, UseCaseDeps

pytestmark = [pytest.mark.asyncio, pytest.mark.uc]

PARENT_DAY = date(2026, 5, 5)
HOTEL_DAY = date(2026, 3, 8)
CAR_DAY = date(2026, 3, 12)
BUY_DAY = date(2026, 3, 19)


@pytest.fixture
async def user(fake_uow_factory: FakeUowFactory, fake_clock: FakeClock) -> User:
    created = User.create(username="wesley", email="wesley@test.com")
    await fake_uow_factory().users.add(created)
    fake_clock.set_time(datetime(2026, 3, 5, 7, tzinfo=UTC))
    return created


async def _create(
    deps: UseCaseDeps, user: User, title: str, **kwargs: object
) -> TaskOutputDTO:
    return await CreateTaskUseCase(**deps).execute(
        CreateTaskInputDTO(user_id=str(user.id), title=title, **kwargs)  # type: ignore[arg-type]
    )


async def _trip(
    deps: UseCaseDeps, user: User, planned: int | None = None
) -> dict[str, TaskOutputDTO]:
    """The trip and its three steps; ``planned``: the parent's estimate
    (None: the subtasks' sum, 4h30)."""
    trip = await _create(
        deps, user, "Organize the trip", due_date="2026-05-05", estimated_minutes=30
    )
    tasks = {"trip": trip}
    for name, day, minutes in (
        ("car", "2026-03-12", 30),
        ("hotel", "2026-03-08", 60),
        ("buy", "2026-03-19", 180),
    ):
        tasks[name] = await _create(
            deps,
            user,
            name,
            parent_id=trip.id,
            due_date=day,
            estimated_minutes=minutes,
        )
    if planned is not None:
        await _edit(deps, user, trip, estimated_minutes=planned)
    return tasks


async def _edit(
    deps: UseCaseDeps, user: User, task: TaskOutputDTO, **kwargs: object
) -> TaskOutputDTO:
    return await UpdateTaskUseCase(**deps).execute(
        UpdateTaskInputDTO(user_id=str(user.id), task_id_prefix=task.id, **kwargs)  # type: ignore[arg-type]
    )


async def _cancel(deps: UseCaseDeps, user: User, task: TaskOutputDTO) -> None:
    await CancelTaskUseCase(**deps).execute(
        CancelTaskInputDTO(user_id=str(user.id), task_id_prefix=task.id)
    )


async def _done(deps: UseCaseDeps, user: User, task: TaskOutputDTO) -> None:
    await CompleteTaskUseCase(**deps).execute(
        TaskByUserRequest(user_id=str(user.id), task_id_prefix=task.id)
    )


async def _loads(
    uow_factory: FakeUowFactory, clock: FakeClock, user: User, *days: date
) -> list[int]:
    async with uow_factory() as uow:
        return [
            (
                await day_load(uow, user.id, user.preferences, d, clock.now())
            ).planned_minutes
            for d in days
        ]


DAYS = (HOTEL_DAY, CAR_DAY, BUY_DAY, PARENT_DAY)


# --- Each one on its own day ----------------------------------------------------


async def test_the_owners_trip(
    use_case_context: UseCaseDeps,
    user: User,
    fake_uow_factory: FakeUowFactory,
    fake_clock: FakeClock,
) -> None:
    await _trip(use_case_context, user)

    # Each step on its day; the parent's 4h30 is theirs: nothing of its own
    assert await _loads(fake_uow_factory, fake_clock, user, *DAYS) == [60, 30, 180, 0]


async def test_a_parent_planning_more_than_its_subtasks(
    use_case_context: UseCaseDeps,
    user: User,
    fake_uow_factory: FakeUowFactory,
    fake_clock: FakeClock,
) -> None:
    await _trip(use_case_context, user, planned=360)

    assert await _loads(fake_uow_factory, fake_clock, user, *DAYS) == [60, 30, 180, 90]


async def test_a_done_or_cancelled_subtask_no_longer_counts(
    use_case_context: UseCaseDeps,
    user: User,
    fake_uow_factory: FakeUowFactory,
    fake_clock: FakeClock,
) -> None:
    trip = await _trip(use_case_context, user, planned=360)

    await _cancel(use_case_context, user, trip["hotel"])
    await _done(use_case_context, user, trip["car"])

    # Neither comes back on the parent's day: its part stays 6h - 4h30
    assert await _loads(fake_uow_factory, fake_clock, user, *DAYS) == [0, 0, 180, 90]


async def test_every_subtask_done_leaves_the_parent_its_own_part(
    use_case_context: UseCaseDeps,
    user: User,
    fake_uow_factory: FakeUowFactory,
    fake_clock: FakeClock,
) -> None:
    trip = await _trip(use_case_context, user)
    for name in ("hotel", "car", "buy"):
        await _done(use_case_context, user, trip[name])

    assert await _loads(fake_uow_factory, fake_clock, user, *DAYS) == [0, 0, 0, 0]


async def test_some_done_and_the_rest_cancelled_is_its_own_part(
    use_case_context: UseCaseDeps,
    user: User,
    fake_uow_factory: FakeUowFactory,
    fake_clock: FakeClock,
) -> None:
    """The owner, 2026-10-17: with one done, the plan moved — the one
    cancelled last does not become the parent's."""
    trip = await _trip(use_case_context, user)
    await _done(use_case_context, user, trip["car"])
    await _cancel(use_case_context, user, trip["hotel"])
    await _cancel(use_case_context, user, trip["buy"])

    assert await _loads(fake_uow_factory, fake_clock, user, PARENT_DAY) == [0]


# --- Every one cancelled -----------------------------------------------------------


async def test_every_one_cancelled_with_an_extra_counts_the_extra(
    use_case_context: UseCaseDeps,
    user: User,
    fake_uow_factory: FakeUowFactory,
    fake_clock: FakeClock,
) -> None:
    trip = await _trip(use_case_context, user, planned=360)
    for name in ("hotel", "car", "buy"):
        await _cancel(use_case_context, user, trip[name])

    assert await _loads(fake_uow_factory, fake_clock, user, *DAYS) == [0, 0, 0, 90]


async def test_every_one_cancelled_without_one_counts_the_last(
    use_case_context: UseCaseDeps,
    user: User,
    fake_uow_factory: FakeUowFactory,
    fake_clock: FakeClock,
) -> None:
    trip = await _trip(use_case_context, user)
    for name in ("car", "hotel", "buy"):
        await _cancel(use_case_context, user, trip[name])

    # The last step left became the parent's: buying, 3h
    assert await _loads(fake_uow_factory, fake_clock, user, *DAYS) == [0, 0, 0, 180]

    # One reopened: the plain rule again, on its own day
    await ReopenTaskUseCase(**use_case_context).execute(
        TaskByUserRequest(user_id=str(user.id), task_id_prefix=trip["hotel"].id)
    )
    assert await _loads(fake_uow_factory, fake_clock, user, *DAYS) == [60, 0, 0, 0]

    # Cancelled again, it is the last one now
    await _cancel(use_case_context, user, trip["hotel"])
    assert await _loads(fake_uow_factory, fake_clock, user, PARENT_DAY) == [60]


async def test_a_parent_whose_subtask_is_deleted_counts_whole(
    use_case_context: UseCaseDeps,
    user: User,
    fake_uow_factory: FakeUowFactory,
    fake_clock: FakeClock,
) -> None:
    """No subtask left: the parent's whole estimate, as before (a deleted
    one is not there at all)."""
    parent = await _create(
        use_case_context, user, "Alone", due_date="2026-05-05", estimated_minutes=45
    )
    sub = await _create(
        use_case_context,
        user,
        "Gone",
        parent_id=parent.id,
        due_date="2026-03-08",
        estimated_minutes=60,
    )
    await DeleteTaskUseCase(**use_case_context).execute(
        DeleteTaskInputDTO(user_id=str(user.id), task_id_prefix=sub.id)
    )

    # Its estimate grew to cover the subtask, and stays (the plan)
    assert await _loads(fake_uow_factory, fake_clock, user, HOTEL_DAY, PARENT_DAY) == [
        0,
        60,
    ]


# --- Late, same day, repeating -----------------------------------------------


async def test_a_late_subtask_counts_today(
    use_case_context: UseCaseDeps, user: User, fake_clock: FakeClock
) -> None:
    trip = await _create(
        use_case_context, user, "Trip", due_date="2026-05-05", estimated_minutes=30
    )
    await _create(
        use_case_context,
        user,
        "Call the agency",
        parent_id=trip.id,
        due_date="yesterday 10:00",
        estimated_minutes=40,
    )

    day = await TodayUseCase(**use_case_context).execute(
        TodayRequest(user_id=str(user.id))
    )

    assert day.load is not None and day.load.planned_minutes == 40


async def test_a_subtask_due_with_its_parent_leaves_the_day_as_it_was(
    use_case_context: UseCaseDeps,
    user: User,
    fake_uow_factory: FakeUowFactory,
    fake_clock: FakeClock,
) -> None:
    party = await _create(
        use_case_context, user, "Party", due_date="2026-03-07", estimated_minutes=90
    )
    await AddSubtasksUseCase(**use_case_context).execute(
        AddSubtasksInputDTO(
            user_id=str(user.id),
            parent_id=party.id,
            titles=["Cake", "Music"],
            estimated_minutes=30,
        )
    )

    # 30m of its own and 2 x 30m of its subtasks: 1h30, as before
    assert await _loads(fake_uow_factory, fake_clock, user, date(2026, 3, 7)) == [90]


async def test_a_recurring_parent_brings_the_rule_along(
    use_case_context: UseCaseDeps,
    user: User,
    fake_uow_factory: FakeUowFactory,
    fake_clock: FakeClock,
) -> None:
    routine = await _create(
        use_case_context,
        user,
        "Morning routine",
        estimated_minutes=60,
        recurrence=RecurrenceInputDTO(
            frequency=RecurrenceInterval.DAILY, start_date="today 09:00"
        ),
    )
    await AddSubtasksUseCase(**use_case_context).execute(
        AddSubtasksInputDTO(
            user_id=str(user.id),
            parent_id=routine.id,
            titles=["Stretch", "Read"],
            estimated_minutes=20,
        )
    )
    today, tomorrow = date(2026, 3, 5), date(2026, 3, 6)
    assert await _loads(fake_uow_factory, fake_clock, user, today) == [60]

    await _done(use_case_context, user, routine)
    # What the handler does after it (the fake bus runs no handlers)
    async with fake_uow_factory() as uow:
        completion = next(
            e
            for e in await uow.task_history.recent(user.id)
            if e.action == TaskAction.COMPLETED and str(e.task_id) == routine.id
        )
        done = await uow.tasks.get_by_id(TaskId.from_string(routine.id))
    assert done is not None
    await CreateRecurringTaskHandler(fake_uow_factory()).handle(
        TaskCompletedEvent(
            id=UniqueId(completion.entry_id),
            occurred_at=completion.occurred_at,
            task_id=done.id,
            user_id=user.id,
            estimated_minutes=60,
            actual_minutes=0,
            energy_level_used=done.required_energy_level,
            task_complexity=done.complexity,
        )
    )

    # The next one, with its steps on its day: 20m of its own and 2 x 20m
    assert await _loads(fake_uow_factory, fake_clock, user, today, tomorrow) == [0, 60]


# --- The warning on the days it fills ------------------------------------------------


async def test_a_subtask_warns_on_its_own_day(
    use_case_context: UseCaseDeps, user: User
) -> None:
    await _create(
        use_case_context, user, "Big", due_date="2026-03-08", estimated_minutes=795
    )
    trip = await _create(
        use_case_context, user, "Trip", due_date="2026-05-05", estimated_minutes=30
    )

    hotel = await _create(
        use_case_context,
        user,
        "Hotel",
        parent_id=trip.id,
        due_date="2026-03-08",
        estimated_minutes=60,
    )
    assert hotel.full_day is not None
    assert (hotel.full_day.day, hotel.full_day.planned_minutes) == (HOTEL_DAY, 855)

    added = await AddSubtasksUseCase(**use_case_context).execute(
        AddSubtasksInputDTO(
            user_id=str(user.id),
            parent_id=trip.id,
            titles=["Car"],
            due_date="2026-03-12",
        )
    )
    assert added.full_day is None  # its own day is empty


async def test_a_change_to_a_parents_part_warns_on_its_day(
    use_case_context: UseCaseDeps, user: User
) -> None:
    await _create(
        use_case_context, user, "Big", due_date="2026-05-05", estimated_minutes=780
    )
    trip = await _trip(use_case_context, user)

    # A smaller step leaves the plan to the parent: 4h30 - 3h30 = 1h
    smaller = await _edit(use_case_context, user, trip["buy"], estimated_minutes=60)
    assert smaller.full_day is not None
    assert (smaller.full_day.day, smaller.full_day.planned_minutes) == (
        PARENT_DAY,
        780 + 120,
    )


async def test_cancelling_the_last_subtask_warns_on_the_parents_day(
    use_case_context: UseCaseDeps, user: User
) -> None:
    await _create(
        use_case_context, user, "Big", due_date="2026-05-05", estimated_minutes=780
    )
    trip = await _trip(use_case_context, user)
    for name in ("car", "hotel"):
        await _cancel(use_case_context, user, trip[name])

    last = await CancelTaskUseCase(**use_case_context).execute(
        CancelTaskInputDTO(user_id=str(user.id), task_id_prefix=trip["buy"].id)
    )

    assert last.full_day is not None
    assert (last.full_day.day, last.full_day.planned_minutes) == (PARENT_DAY, 960)


async def test_moving_a_parent_warns_where_its_subtasks_follow(
    use_case_context: UseCaseDeps, user: User
) -> None:
    await _create(
        use_case_context, user, "Big", due_date="2026-03-09", estimated_minutes=790
    )
    party = await _create(
        use_case_context, user, "Party", due_date="2026-03-07", estimated_minutes=10
    )
    await AddSubtasksUseCase(**use_case_context).execute(
        AddSubtasksInputDTO(
            user_id=str(user.id),
            parent_id=party.id,
            titles=["Cake"],
            estimated_minutes=30,
        )
    )

    moved = await _edit(use_case_context, user, party, due_date="2026-03-09")

    # The parent counts nothing of its own; the cake, moved with it, fills it
    assert moved.full_day is not None
    assert moved.full_day.planned_minutes == 820


async def test_a_subtask_moved_out_warns_on_the_parent_it_left(
    use_case_context: UseCaseDeps, user: User
) -> None:
    await _create(
        use_case_context, user, "Big", due_date="2026-05-05", estimated_minutes=780
    )
    trip = await _trip(use_case_context, user)

    alone = await _edit(use_case_context, user, trip["buy"], remove_parent=True)

    # Its 3h are the trip's own now (4h30 planned, 1h30 of subtasks left)
    assert alone.full_day is not None
    assert (alone.full_day.day, alone.full_day.planned_minutes) == (PARENT_DAY, 960)


# --- Shown: the own part and the subtasks counted -----------------------------------


async def test_the_card_shows_the_own_part(
    use_case_context: UseCaseDeps, user: User
) -> None:
    trip = await _trip(use_case_context, user, planned=360)
    get = GetTaskUseCase(**use_case_context)

    card = await get.execute(
        GetTaskRequest(user_id=str(user.id), task_id_prefix=trip["trip"].id)
    )
    hotel = await get.execute(
        GetTaskRequest(user_id=str(user.id), task_id_prefix=trip["hotel"].id)
    )

    assert (card.own_minutes, card.estimated_minutes) == (90, 360)
    assert hotel.own_minutes is None  # a subtask: all of it is its own


async def test_today_and_wrap_show_a_parents_part(
    use_case_context: UseCaseDeps, user: User, fake_clock: FakeClock
) -> None:
    party = await _create(
        use_case_context, user, "Party", due_date="today 18:00", estimated_minutes=90
    )
    await AddSubtasksUseCase(**use_case_context).execute(
        AddSubtasksInputDTO(
            user_id=str(user.id),
            parent_id=party.id,
            titles=["Cake", "Music"],
            estimated_minutes=30,
        )
    )
    [cake, _] = (
        await GetTaskUseCase(**use_case_context).execute(
            GetTaskRequest(user_id=str(user.id), task_id_prefix=party.id)
        )
    ).subtasks
    await _done(use_case_context, user, cake)  # type: ignore[arg-type]
    await _create(
        use_case_context, user, "Alone", due_date="today 20:00", estimated_minutes=20
    )

    day = await TodayUseCase(**use_case_context).execute(
        TodayRequest(user_id=str(user.id))
    )

    shown = {t.title: t for t in day.today}
    assert (shown["Party"].own_minutes, shown["Party"].estimated_minutes) == (30, 90)
    assert (shown["Party"].open_subtasks, shown["Party"].all_subtasks) == (1, 2)
    assert shown["Music"].own_minutes is None
    assert shown["Alone"].own_minutes is None and shown["Alone"].all_subtasks == 0
    # The load counts the parts: 30 + the music's 30 + 20
    assert day.load is not None and day.load.planned_minutes == 80

    fake_clock.set_time(datetime(2026, 3, 5, 21, tzinfo=UTC))
    wrap = await WrapUseCase(**use_case_context).execute(
        WrapRequest(user_id=str(user.id))
    )
    [left] = [i.task for i in wrap.left if i.task.title == "Party"]
    assert (left.own_minutes, left.open_subtasks) == (30, 1)
