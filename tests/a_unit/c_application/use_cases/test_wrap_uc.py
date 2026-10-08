"""The end of the day: what was done, what is left and what can be done
with each, and a few tasks ahead when nothing is left.

The fake clock is moved to Thursday 2026-03-05, 20:00 by hand; the user is
in UTC and a task lasts an hour unless a test says otherwise.
"""

from datetime import UTC, datetime

import pytest

from b_domain.entities import User
from b_domain.value_objects import RecurrenceInterval
from c_application.dtos.recurrence_dtos import RecurrenceInputDTO
from c_application.dtos.task_dtos import (
    AddSubtasksInputDTO,
    CreateTaskInputDTO,
    TaskByUserRequest,
    TaskOutputDTO,
    UpdateTaskInputDTO,
)
from c_application.use_cases import (
    AddSubtasksUseCase,
    CompleteTaskUseCase,
    CreateTaskUseCase,
    SnoozeTaskUseCase,
    UpdateTaskUseCase,
    WrapUseCase,
)
from c_application.use_cases.task.snooze import SnoozeTaskRequest
from c_application.use_cases.task.wrap import WrapAction, WrapOutputDTO, WrapRequest
from tests.conftest import FakeClock, FakeUowFactory, UseCaseDeps

pytestmark = [pytest.mark.asyncio, pytest.mark.uc]

A = WrapAction


@pytest.fixture
async def user(fake_uow_factory: FakeUowFactory, fake_clock: FakeClock) -> User:
    created = User.create(username="wesley", email="wesley@test.com")
    await fake_uow_factory().users.add(created)
    fake_clock.set_time(datetime(2026, 3, 5, 20, 0, tzinfo=UTC))
    return created


async def _create(
    deps: UseCaseDeps, user: User, title: str, **kwargs: object
) -> TaskOutputDTO:
    return await CreateTaskUseCase(**deps).execute(
        CreateTaskInputDTO(user_id=str(user.id), title=title, **kwargs)  # type: ignore[arg-type]
    )


async def _wrap(deps: UseCaseDeps, user: User, **kwargs: object) -> WrapOutputDTO:
    return await WrapUseCase(**deps).execute(
        WrapRequest(user_id=str(user.id), **kwargs)  # type: ignore[arg-type]
    )


def _daily(start: str) -> RecurrenceInputDTO:
    return RecurrenceInputDTO(frequency=RecurrenceInterval.DAILY, start_date=start)


async def test_done_and_left_each_with_what_fits_it(
    use_case_context: UseCaseDeps, user: User
) -> None:
    done = await _create(use_case_context, user, "Trash", due_date="today 08:00")
    await CompleteTaskUseCase(**use_case_context).execute(
        TaskByUserRequest(task_id_prefix=done.id[:8], user_id=str(user.id))
    )
    await _create(use_case_context, user, "Bill", due_date="yesterday 18:00")
    await _create(use_case_context, user, "Gym", recurrence=_daily("today 18:00"))
    await _create(use_case_context, user, "Tomorrow", due_date="tomorrow 09:00")
    await _create(use_case_context, user, "Undated")

    wrap = await _wrap(use_case_context, user)

    assert [t.title for t in wrap.done] == ["Trash"]
    by_title = {item.task.title: item.actions for item in wrap.left}
    assert list(by_title) == ["Bill", "Gym"]
    assert by_title["Bill"] == [
        A.TOMORROW,
        A.BUSINESS_DAY,
        A.DATE,
        A.REMOVE_DATE,
        A.CANCEL,
        A.DONE,
        A.KEEP,
    ]
    # Tomorrow is its next one's day: skipped, never without a date
    assert by_title["Gym"] == [A.DATE, A.SKIP, A.DONE, A.KEEP]
    assert wrap.ahead == []


async def test_a_weekly_one_can_go_to_tomorrow(
    use_case_context: UseCaseDeps, user: User
) -> None:
    await _create(
        use_case_context,
        user,
        "Review",
        recurrence=RecurrenceInputDTO(
            frequency=RecurrenceInterval.WEEKLY, start_date="today 09:00"
        ),
    )
    [item] = (await _wrap(use_case_context, user)).left
    assert item.actions[:2] == [A.TOMORROW, A.BUSINESS_DAY]
    assert A.SKIP in item.actions and A.REMOVE_DATE not in item.actions


async def test_moved_ones_are_gone_kept_ones_come_back(
    use_case_context: UseCaseDeps, user: User
) -> None:
    """No state: each run is what is left now."""
    moved = await _create(use_case_context, user, "Moved", due_date="today 10:00")
    await _create(use_case_context, user, "Kept", due_date="today 11:00")
    assert len((await _wrap(use_case_context, user)).left) == 2

    await SnoozeTaskUseCase(**use_case_context).execute(
        SnoozeTaskRequest(user_id=str(user.id), task_id_prefix=moved.id[:8])
    )

    assert [i.task.title for i in (await _wrap(use_case_context, user)).left] == [
        "Kept"
    ]


async def test_a_subtask_goes_with_its_parent(
    use_case_context: UseCaseDeps, user: User
) -> None:
    trip = await _create(use_case_context, user, "Trip", due_date="today 12:00")
    await AddSubtasksUseCase(**use_case_context).execute(
        AddSubtasksInputDTO(
            user_id=str(user.id), parent_id=trip.id[:8], titles=["Pack"]
        )
    )
    later = await _create(use_case_context, user, "Later", due_date="2026-03-10 12:00")
    added = await AddSubtasksUseCase(**use_case_context).execute(
        AddSubtasksInputDTO(
            user_id=str(user.id),
            parent_id=later.id[:8],
            titles=["Book"],
            due_date="today 09:00",
        )
    )

    wrap = await _wrap(use_case_context, user)

    by_title = {item.task.title: item.actions for item in wrap.left}
    # Pack goes with Trip; Book is late on its own, under a later parent
    assert list(by_title) == ["Book", "Trip"]
    assert added.subtasks[0].title == "Book"
    assert A.REMOVE_DATE not in by_title["Book"]
    assert A.TOMORROW in by_title["Book"]


async def test_a_subtask_never_offered_past_its_parent(
    use_case_context: UseCaseDeps, user: User
) -> None:
    parent = await _create(use_case_context, user, "Parent", due_date="tomorrow 08:00")
    await AddSubtasksUseCase(**use_case_context).execute(
        AddSubtasksInputDTO(
            user_id=str(user.id),
            parent_id=parent.id[:8],
            titles=["Early"],
            due_date="today 09:00",
        )
    )
    [item] = (await _wrap(use_case_context, user)).left
    assert A.TOMORROW not in item.actions and A.DATE in item.actions


async def test_a_waiting_one_cannot_be_done(
    use_case_context: UseCaseDeps, user: User
) -> None:
    first = await _create(use_case_context, user, "First", due_date="tomorrow 09:00")
    await _create(
        use_case_context,
        user,
        "Second",
        due_date="today 09:00",
        depends_on={first.id[:8]},
    )
    [item] = (await _wrap(use_case_context, user)).left
    assert A.DONE not in item.actions


async def test_nothing_left_offers_the_shortest_ahead(
    use_case_context: UseCaseDeps, user: User
) -> None:
    for title, due, minutes in [
        ("Long", "tomorrow 09:00", 120),
        ("Quick", "2026-03-08 09:00", 10),
        ("Medium", "tomorrow 10:00", 45),
        ("Too far", "2026-03-30 09:00", 5),  # past days_ahead (7)
        ("Same", "2026-03-07 09:00", 45),
    ]:
        await _create(
            use_case_context, user, title, due_date=due, estimated_minutes=minutes
        )
    blocker = await _create(use_case_context, user, "Blocker", due_date="tomorrow")
    waits = await _create(
        use_case_context, user, "Waits", due_date="tomorrow", estimated_minutes=1
    )
    await UpdateTaskUseCase(**use_case_context).execute(
        UpdateTaskInputDTO(
            user_id=str(user.id),
            task_id_prefix=waits.id[:8],
            add_dependencies=[blocker.id[:8]],
        )
    )

    wrap = await _wrap(use_case_context, user, ahead_count=4)

    assert wrap.left == []
    # Waits (1 min) waits on Blocker: it cannot be done now
    assert [t.title for t in wrap.ahead] == ["Quick", "Medium", "Same", "Blocker"]
