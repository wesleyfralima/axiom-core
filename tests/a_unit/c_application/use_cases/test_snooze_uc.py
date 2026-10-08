"""The snooze: put off what is due today, or late, to later.

The fake clock is moved to Thursday 2026-03-05, 07:00 by hand; the user is
in UTC and a task lasts an hour unless a test says otherwise.
"""

from datetime import UTC, datetime

import pytest

from a_core.exceptions import ValidationException
from b_domain.entities import User
from b_domain.exceptions.snooze import SnoozeRefusal, SnoozeRefusedError
from b_domain.ports.repositories.filters import TaskFilter
from b_domain.value_objects import RecurrenceInterval, TaskId
from b_domain.value_objects.task_history import TaskAction
from c_application.dtos.recurrence_dtos import RecurrenceInputDTO
from c_application.dtos.task_dtos import (
    AddSubtasksInputDTO,
    CreateTaskInputDTO,
    TaskByUserRequest,
    TaskHistoryRequest,
    TaskOutputDTO,
)
from c_application.use_cases import (
    AddSubtasksUseCase,
    CompleteTaskUseCase,
    CreateTaskUseCase,
    GetTaskHistoryUseCase,
    SnoozeTaskUseCase,
    UndoPreviewUseCase,
    UndoUseCase,
)
from c_application.use_cases.task.snooze import SnoozedTaskOutputDTO, SnoozeTaskRequest
from c_application.use_cases.task.undo import UndoRequest
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
    deps: UseCaseDeps, user: User, title: str = "Call", **kwargs: object
) -> TaskOutputDTO:
    return await CreateTaskUseCase(**deps).execute(
        CreateTaskInputDTO(user_id=str(user.id), title=title, **kwargs)  # type: ignore[arg-type]
    )


async def _snooze(
    deps: UseCaseDeps, user: User, task: TaskOutputDTO, **kwargs: object
) -> SnoozedTaskOutputDTO:
    return await SnoozeTaskUseCase(**deps).execute(
        SnoozeTaskRequest(user_id=str(user.id), task_id_prefix=task.id[:8], **kwargs)  # type: ignore[arg-type]
    )


def _daily(start: str) -> RecurrenceInputDTO:
    return RecurrenceInputDTO(frequency=RecurrenceInterval.DAILY, start_date=start)


# --- Where it goes ----------------------------------------------------------


async def test_to_the_next_day_at_the_same_time(
    use_case_context: UseCaseDeps, user: User
) -> None:
    task = await _create(use_case_context, user, due_date="today 08:00")

    snoozed = await _snooze(use_case_context, user, task)

    assert snoozed.task.due_date == datetime(2026, 3, 6, 8, 0)
    assert snoozed.task.snoozed_from == datetime(2026, 3, 5, 8, 0)
    assert snoozed.next is None


async def test_snoozed_again_it_remembers_where_it_was_first(
    use_case_context: UseCaseDeps, user: User, fake_clock: FakeClock
) -> None:
    task = await _create(use_case_context, user, due_date="today 08:00")
    await _snooze(use_case_context, user, task, minutes=60)

    again = await _snooze(use_case_context, user, task, minutes=30)

    assert again.task.due_date == datetime(2026, 3, 5, 9, 30)
    assert again.task.snoozed_from == datetime(2026, 3, 5, 8, 0)


@pytest.mark.parametrize(
    ("due", "minutes", "lands"),
    [
        ("today 08:00", 120, datetime(2026, 3, 5, 10, 0)),  # from the due date
        ("yesterday 18:00", 120, datetime(2026, 3, 5, 9, 0)),  # late: from now
    ],
)
async def test_by_some_time_from_the_later_of_now_and_the_due_date(
    use_case_context: UseCaseDeps,
    user: User,
    due: str,
    minutes: int,
    lands: datetime,
) -> None:
    task = await _create(use_case_context, user, due_date=due)
    snoozed = await _snooze(use_case_context, user, task, minutes=minutes)
    assert snoozed.task.due_date == lands


@pytest.mark.parametrize(
    ("typed", "lands"),
    [
        ("15:00", datetime(2026, 3, 5, 15, 0)),  # a time alone is today
        ("tomorrow", datetime(2026, 3, 6, 8, 0)),  # a day keeps its time
        ("2026-03-10", datetime(2026, 3, 10, 8, 0)),
        ("tomorrow 09:30", datetime(2026, 3, 6, 9, 30)),
    ],
)
async def test_to_a_moment_typed(
    use_case_context: UseCaseDeps, user: User, typed: str, lands: datetime
) -> None:
    task = await _create(use_case_context, user, due_date="today 08:00")
    snoozed = await _snooze(use_case_context, user, task, to=typed)
    assert snoozed.task.due_date == lands


async def test_the_next_business_day(
    use_case_context: UseCaseDeps, user: User, fake_clock: FakeClock
) -> None:
    fake_clock.set_time(_at(7, day=6))  # Friday
    task = await _create(use_case_context, user, due_date="today 08:00")

    business = await _snooze(use_case_context, user, task, business_day=True)

    assert business.task.due_date == datetime(2026, 3, 9, 8, 0)  # Monday


async def test_any_next_day_by_default(
    use_case_context: UseCaseDeps, user: User, fake_clock: FakeClock
) -> None:
    fake_clock.set_time(_at(7, day=6))  # Friday
    task = await _create(use_case_context, user, due_date="today 08:00")
    snoozed = await _snooze(use_case_context, user, task)
    assert snoozed.task.due_date == datetime(2026, 3, 7, 8, 0)  # Saturday


async def test_a_fixed_due_date_keeps_its_kind(
    use_case_context: UseCaseDeps, user: User
) -> None:
    task = await _create(
        use_case_context, user, due_date="today 08:00", is_floating=False
    )
    snoozed = await _snooze(use_case_context, user, task)
    assert snoozed.task.due_date == datetime(2026, 3, 6, 8, 0, tzinfo=UTC)


# --- What is refused --------------------------------------------------------


async def test_only_an_open_task_due_today_or_late(
    use_case_context: UseCaseDeps, user: User
) -> None:
    done = await _create(use_case_context, user, "Done", due_date="today 08:00")
    await CompleteTaskUseCase(**use_case_context).execute(
        TaskByUserRequest(task_id_prefix=done.id[:8], user_id=str(user.id))
    )
    undated = await _create(use_case_context, user, "Undated")
    later = await _create(use_case_context, user, "Later", due_date="tomorrow 08:00")

    for task, reason, says in [
        (done, SnoozeRefusal.CLOSED, "'Done' is done"),
        (undated, SnoozeRefusal.NO_DUE, "has no due date"),
        (later, SnoozeRefusal.NOT_DUE_YET, "due Fri Mar 06 08:00, after today"),
    ]:
        with pytest.raises(SnoozeRefusedError, match=says) as refused:
            await _snooze(use_case_context, user, task)
        assert refused.value.reason == reason


@pytest.mark.parametrize(
    ("typed", "says"),
    [
        ("06:00", "Thu Mar 05 06:00 is not after Thu Mar 05 08:00"),
        ("07:30", "is not after Thu Mar 05 08:00"),
    ],
)
async def test_only_later(
    use_case_context: UseCaseDeps, user: User, typed: str, says: str
) -> None:
    task = await _create(use_case_context, user, due_date="today 08:00")
    with pytest.raises(SnoozeRefusedError, match=says) as refused:
        await _snooze(use_case_context, user, task, to=typed)
    assert refused.value.reason == SnoozeRefusal.NOT_LATER


async def test_a_late_task_only_after_now(
    use_case_context: UseCaseDeps, user: User
) -> None:
    task = await _create(use_case_context, user, due_date="yesterday 18:00")
    with pytest.raises(SnoozeRefusedError, match="is not after now"):
        await _snooze(use_case_context, user, task, to="06:30")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"to": "15:00", "minutes": 30},
        {"to": "tomorrow", "business_day": True},
        {"minutes": 30, "business_day": True},
    ],
)
async def test_one_way_of_saying_when(
    use_case_context: UseCaseDeps, user: User, kwargs: dict[str, object]
) -> None:
    task = await _create(use_case_context, user, due_date="today 08:00")
    with pytest.raises(ValidationException, match="Say when once"):
        await _snooze(use_case_context, user, task, **kwargs)


async def test_some_time_is_more_than_nothing(
    use_case_context: UseCaseDeps, user: User
) -> None:
    task = await _create(use_case_context, user, due_date="today 08:00")
    with pytest.raises(ValidationException, match="more than 0 minutes"):
        await _snooze(use_case_context, user, task, minutes=0)


# --- Recurring tasks ---------------------------------------------------------


async def test_a_recurring_one_within_its_day_keeps_its_rule(
    use_case_context: UseCaseDeps, user: User
) -> None:
    gym = await _create(use_case_context, user, "Gym", recurrence=_daily("today 06:30"))

    snoozed = await _snooze(use_case_context, user, gym, to="18:00")

    assert snoozed.task.due_date == datetime(2026, 3, 5, 18, 0)
    assert snoozed.task.recurrence is not None
    assert snoozed.next is None


async def test_onto_the_next_ones_day_is_refused(
    use_case_context: UseCaseDeps, user: User
) -> None:
    gym = await _create(use_case_context, user, "Gym", recurrence=_daily("today 06:30"))

    for kwargs in ({}, {"to": "2026-03-07"}, {"to": "tomorrow 05:00"}):
        with pytest.raises(
            SnoozeRefusedError, match="The next 'Gym' is Fri Mar 06 06:30"
        ) as refused:
            await _snooze(use_case_context, user, gym, **kwargs)
        assert refused.value.reason == SnoozeRefusal.LANDS_ON_NEXT
        assert refused.value.next_due == datetime(2026, 3, 6, 6, 30)


async def test_keeping_both_moves_the_series_on(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    gym = await _create(use_case_context, user, "Gym", recurrence=_daily("today 06:30"))

    snoozed = await _snooze(use_case_context, user, gym, keep_both=True)

    # The snoozed one leaves the series, a one-off still in it
    assert snoozed.task.due_date == datetime(2026, 3, 6, 6, 30)
    assert snoozed.task.recurrence is None
    assert snoozed.task.series_id == gym.series_id
    # The series moved on: its next occurrence is there now
    assert snoozed.next is not None
    assert snoozed.next.due_date == datetime(2026, 3, 6, 6, 30)
    assert snoozed.next.recurrence is not None
    assert snoozed.next.series_id == gym.series_id
    async with fake_uow_factory() as uow:
        series = await uow.tasks.list(TaskFilter(user_id=user.id, in_series=True))
    assert len(series) == 2


async def test_undo_takes_both_back(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    gym = await _create(use_case_context, user, "Gym", recurrence=_daily("today 06:30"))
    snoozed = await _snooze(use_case_context, user, gym, keep_both=True)
    assert snoozed.next is not None

    preview = await UndoPreviewUseCase(**use_case_context).execute(
        UndoRequest(user_id=str(user.id))
    )
    assert preview.entry_id is not None
    await UndoUseCase(**use_case_context).execute(
        UndoRequest(user_id=str(user.id), entry_id=preview.entry_id)
    )

    async with fake_uow_factory() as uow:
        back = await uow.tasks.get_by_id(TaskId.from_string(gym.id))
        made = await uow.tasks.get_by_id(TaskId.from_string(snoozed.next.id))
    assert back is not None and made is not None
    assert back.due_date is not None
    assert back.due_date.value == datetime(2026, 3, 5, 6, 30)
    assert back.recurrence is not None
    assert back.snoozed_from is None
    assert made.deleted_at is not None


async def test_several_times_a_day_compares_the_time(
    use_case_context: UseCaseDeps, user: User
) -> None:
    """Every 2 hours from 06:00: at 07:00 the next one is 08:00."""
    water = await _create(
        use_case_context,
        user,
        "Water",
        recurrence=RecurrenceInputDTO(
            frequency=RecurrenceInterval.HOURLY, interval=2, start_date="today 06:00"
        ),
        estimated_minutes=5,
    )

    with pytest.raises(
        SnoozeRefusedError, match="The next 'Water' is Thu Mar 05 08:00"
    ):
        await _snooze(use_case_context, user, water, minutes=60)

    snoozed = await _snooze(use_case_context, user, water, minutes=30)
    assert snoozed.task.due_date == datetime(2026, 3, 5, 7, 30)


# --- The history and subtasks -----------------------------------------------


async def test_the_history_says_snoozed(
    use_case_context: UseCaseDeps, user: User
) -> None:
    task = await _create(use_case_context, user, due_date="today 08:00")
    await _snooze(use_case_context, user, task)

    log = await GetTaskHistoryUseCase(**use_case_context).execute(
        TaskHistoryRequest(task_id_prefix=task.id[:8], user_id=str(user.id))
    )

    snoozed = log.entries[-1]
    assert snoozed.action == TaskAction.SNOOZED
    [change] = snoozed.changes
    assert (change.field, change.before, change.after) == (
        "due",
        "2026-03-05T08:00:00",
        "2026-03-06T08:00:00",
    )


async def test_a_parents_subtasks_follow_it(
    use_case_context: UseCaseDeps, user: User
) -> None:
    trip = await _create(use_case_context, user, "Trip", due_date="today 18:00")
    await AddSubtasksUseCase(**use_case_context).execute(
        AddSubtasksInputDTO(
            user_id=str(user.id), parent_id=trip.id[:8], titles=["Pack"]
        )
    )

    snoozed = await _snooze(use_case_context, user, trip)

    assert snoozed.notes == ["'Pack': due date changed with its parent."]


async def test_a_subtask_stays_within_its_parent(
    use_case_context: UseCaseDeps, user: User
) -> None:
    trip = await _create(use_case_context, user, "Trip", due_date="today 18:00")
    added = await AddSubtasksUseCase(**use_case_context).execute(
        AddSubtasksInputDTO(
            user_id=str(user.id), parent_id=trip.id[:8], titles=["Pack"]
        )
    )

    with pytest.raises(ValidationException, match="no later than its parent"):
        await _snooze(use_case_context, user, added.subtasks[0])


async def test_both_kept_the_next_one_brings_the_subtasks_to_its_day(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    bedtime = await _create(
        use_case_context, user, "Bedtime", recurrence=_daily("today 22:00")
    )
    await AddSubtasksUseCase(**use_case_context).execute(
        AddSubtasksInputDTO(
            user_id=str(user.id), parent_id=bedtime.id[:8], titles=["Stretch"]
        )
    )

    snoozed = await _snooze(use_case_context, user, bedtime, keep_both=True)

    assert snoozed.next is not None
    async with fake_uow_factory() as uow:
        for parent in (bedtime.id, snoozed.next.id):
            [sub] = await uow.tasks.get_subtasks(TaskId.from_string(parent))
            assert sub.due_date is not None
            assert sub.due_date.value == datetime(2026, 3, 6, 22, 0)
