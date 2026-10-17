"""A series that keeps its missed occurrences (the default: each one is
there to be recorded) or catches up, skipping them to the first still on
time — as its rule says, or as one command says, that time.

The fake clock is moved to Thursday 2026-03-05, 07:00 by hand; the user is
in UTC and a task lasts an hour.
"""

from datetime import UTC, datetime

import pytest

from a_core import UniqueId
from a_core.exceptions import ValidationException
from b_domain.entities import User
from b_domain.events.task_events import TaskCancelledEvent, TaskCompletedEvent
from b_domain.ports.repositories.filters import TaskFilter
from b_domain.value_objects import RecurrenceInterval, TaskId
from b_domain.value_objects.recurrences._serial import rule_from_dict, rule_to_dict
from b_domain.value_objects.task_history import TaskAction
from c_application.dtos.recurrence_dtos import RecurrenceInputDTO
from c_application.dtos.task_dtos import (
    CancelTaskInputDTO,
    CreateTaskInputDTO,
    TaskByUserRequest,
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
    SnoozeTaskUseCase,
    UpdateTaskUseCase,
    WrapUseCase,
)
from c_application.use_cases.task.snooze import SnoozeTaskRequest
from c_application.use_cases.task.wrap import WrapAction, WrapRequest
from tests.conftest import FakeClock, FakeUowFactory, UseCaseDeps

pytestmark = [pytest.mark.asyncio, pytest.mark.uc]


@pytest.fixture
async def user(fake_uow_factory: FakeUowFactory, fake_clock: FakeClock) -> User:
    created = User.create(username="wesley", email="wesley@test.com")
    await fake_uow_factory().users.add(created)
    fake_clock.set_time(datetime(2026, 3, 5, 7, 0, tzinfo=UTC))
    return created


async def _daily(
    deps: UseCaseDeps, user: User, start: str, catch_up: bool = False
) -> TaskOutputDTO:
    return await CreateTaskUseCase(**deps).execute(
        CreateTaskInputDTO(
            user_id=str(user.id),
            title="Rent",
            recurrence=RecurrenceInputDTO(
                frequency=RecurrenceInterval.DAILY,
                start_date=start,
                catch_up=catch_up,
            ),
        )
    )


async def _done_and_next(
    deps: UseCaseDeps,
    user: User,
    uow_factory: FakeUowFactory,
    task: TaskOutputDTO | str,
    catch_up: bool | None = None,
) -> datetime:
    """Complete it, run the handler as the relay does; the next one's due."""
    task_id: str = task if isinstance(task, str) else task.id
    await CompleteTaskUseCase(**deps).execute(
        TaskByUserRequest(
            task_id_prefix=task_id[:8], user_id=str(user.id), catch_up=catch_up
        )
    )
    async with uow_factory() as uow:
        [entry] = [
            e
            for e in await uow.task_history.recent(user.id)
            if e.action == TaskAction.COMPLETED and str(e.task_id) == task_id
        ]
        closed = await uow.tasks.get_by_id(TaskId.from_string(task_id))
    assert closed is not None
    await CreateRecurringTaskHandler(uow_factory()).handle(
        TaskCompletedEvent(
            id=UniqueId(entry.entry_id),
            occurred_at=entry.occurred_at,
            task_id=closed.id,
            user_id=user.id,
            estimated_minutes=60,
            actual_minutes=0,
            energy_level_used=closed.required_energy_level,
            task_complexity=closed.complexity,
            catch_up=catch_up,
        )
    )
    return await _the_open_one(uow_factory, user)


async def _the_open_one(uow_factory: FakeUowFactory, user: User) -> datetime:
    async with uow_factory() as uow:
        open_ones = [
            t
            for t in await uow.tasks.list(TaskFilter(user_id=user.id, in_series=True))
            if not t.status.is_closed
        ]
    [following] = open_ones
    assert following.due_date is not None
    return following.due_date.value


async def test_created_catching_up_it_says_so(
    use_case_context: UseCaseDeps, user: User
) -> None:
    habit = await _daily(use_case_context, user, "today 09:00", catch_up=True)
    assert habit.recurrence is not None and habit.recurrence.catch_up
    assert habit.recurrence_display == "Every day, skipping the missed ones."
    rent = await _daily(use_case_context, user, "today 10:00")
    assert rent.recurrence is not None and not rent.recurrence.catch_up
    assert rent.recurrence_display == "Every day."


@pytest.mark.parametrize(
    ("catch_up", "next_due"),
    [
        (False, datetime(2026, 3, 3, 9, 0)),  # the default: the one after, late
        (True, datetime(2026, 3, 5, 9, 0)),  # catching up: the first on time
    ],
)
async def test_done_late_the_next_one(
    use_case_context: UseCaseDeps,
    user: User,
    fake_uow_factory: FakeUowFactory,
    catch_up: bool,
    next_due: datetime,
) -> None:
    rent = await _daily(use_case_context, user, "2026-03-02 09:00", catch_up)
    assert rent.due_date == datetime(2026, 3, 2, 9, 0)

    following = await _done_and_next(use_case_context, user, fake_uow_factory, rent)

    assert following == next_due


@pytest.mark.parametrize(
    ("rule", "this_time", "next_due"),
    [
        (False, True, datetime(2026, 3, 5, 9, 0)),  # skips the missed, once
        (True, False, datetime(2026, 3, 3, 9, 0)),  # keeps them, once
    ],
)
async def test_one_command_decides_for_itself(
    use_case_context: UseCaseDeps,
    user: User,
    fake_uow_factory: FakeUowFactory,
    rule: bool,
    this_time: bool,
    next_due: datetime,
) -> None:
    gym = await _daily(use_case_context, user, "2026-03-02 09:00", rule)

    following = await _done_and_next(
        use_case_context, user, fake_uow_factory, gym, catch_up=this_time
    )

    assert following == next_due
    async with fake_uow_factory() as uow:
        [task] = [
            t
            for t in await uow.tasks.list(TaskFilter(user_id=user.id, in_series=True))
            if not t.status.is_closed
        ]
    assert task.recurrence is not None and task.recurrence.catch_up == rule


async def test_a_skip_can_catch_up_too(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    gym = await _daily(use_case_context, user, "2026-03-02 09:00")
    await CancelTaskUseCase(**use_case_context).execute(
        CancelTaskInputDTO(
            user_id=str(user.id), task_id_prefix=gym.id[:8], catch_up=True
        )
    )
    async with fake_uow_factory() as uow:
        closed = await uow.tasks.get_by_id(TaskId.from_string(gym.id))
    assert closed is not None
    await CreateRecurringTaskHandler(fake_uow_factory()).handle(
        TaskCancelledEvent(
            occurred_at=datetime(2026, 3, 5, 7, 0, tzinfo=UTC),
            task_id=closed.id,
            user_id=user.id,
            catch_up=True,
        )
    )

    assert await _the_open_one(fake_uow_factory, user) == datetime(2026, 3, 5, 9, 0)


async def test_missed_ones_come_one_at_a_time(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    """The owner's case: days without opening the app, then each one told."""
    gym = await _daily(use_case_context, user, "2026-03-02 09:00")

    second = await _done_and_next(use_case_context, user, fake_uow_factory, gym)
    assert second == datetime(2026, 3, 3, 9, 0)
    async with fake_uow_factory() as uow:
        [task] = [
            t
            for t in await uow.tasks.list(TaskFilter(user_id=user.id, in_series=True))
            if not t.status.is_closed
        ]
    third = await _done_and_next(use_case_context, user, fake_uow_factory, str(task.id))
    assert third == datetime(2026, 3, 4, 9, 0)


async def test_a_snoozed_bill_lands_anywhere_and_eats_no_one(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    rent = await _daily(use_case_context, user, "today 06:30")

    # Onto tomorrow, its next one's day: no refusal
    snoozed = await SnoozeTaskUseCase(**use_case_context).execute(
        SnoozeTaskRequest(
            user_id=str(user.id), task_id_prefix=rent.id[:8], to="2026-03-07"
        )
    )
    assert snoozed.task.due_date == datetime(2026, 3, 7, 6, 30)
    assert snoozed.next is None
    assert snoozed.task.recurrence is not None  # still in its series

    # Done: the next is the one after where it was, not after the 7th
    following = await _done_and_next(use_case_context, user, fake_uow_factory, rent)
    assert following == datetime(2026, 3, 6, 6, 30)


async def test_switched_by_an_edit_and_kept_with_a_new_rule(
    use_case_context: UseCaseDeps, user: User
) -> None:
    rent = await _daily(use_case_context, user, "today 09:00")
    update = UpdateTaskUseCase(**use_case_context)

    habit = await update.execute(
        UpdateTaskInputDTO(
            user_id=str(user.id), task_id_prefix=rent.id[:8], catch_up=True
        )
    )
    assert habit.recurrence is not None and habit.recurrence.catch_up

    weekly = await update.execute(
        UpdateTaskInputDTO(
            user_id=str(user.id),
            task_id_prefix=rent.id[:8],
            recurrence=RecurrenceInputDTO(frequency=RecurrenceInterval.WEEKLY),
        )
    )
    assert weekly.recurrence is not None and weekly.recurrence.catch_up

    kept = await update.execute(
        UpdateTaskInputDTO(
            user_id=str(user.id), task_id_prefix=rent.id[:8], catch_up=False
        )
    )
    assert kept.recurrence is not None and not kept.recurrence.catch_up


async def test_only_a_recurring_task(use_case_context: UseCaseDeps, user: User) -> None:
    once = await CreateTaskUseCase(**use_case_context).execute(
        CreateTaskInputDTO(user_id=str(user.id), title="Once", due_date="today 09:00")
    )
    with pytest.raises(ValidationException, match="does not repeat"):
        await UpdateTaskUseCase(**use_case_context).execute(
            UpdateTaskInputDTO(
                user_id=str(user.id), task_id_prefix=once.id[:8], catch_up=True
            )
        )


async def test_wrap_offers_tomorrow_to_a_daily_series(
    use_case_context: UseCaseDeps, user: User
) -> None:
    await _daily(use_case_context, user, "today 06:00")
    [item] = (
        await WrapUseCase(**use_case_context).execute(WrapRequest(user_id=str(user.id)))
    ).left
    assert item.actions[:2] == [WrapAction.TOMORROW, WrapAction.BUSINESS_DAY]
    assert WrapAction.SKIP in item.actions


async def test_the_rule_as_data_keeps_it() -> None:
    from b_domain.value_objects.dates import AxiomDate
    from b_domain.value_objects.recurrences import RecurrenceFactory

    rule = RecurrenceFactory.create_from_input(
        start_date=AxiomDate.floating(datetime(2026, 3, 5, 9, 0), "UTC"),
        frequency=RecurrenceInterval.MONTHLY,
        days_of_month={5},
        catch_up=True,
    )
    assert rule_from_dict(rule_to_dict(rule)).catch_up


async def test_a_rule_stored_before_keeps_its_missed_ones() -> None:
    """Rules stored before 0.39.0 say ``keep_missed`` (false for almost
    all): every one of them keeps its missed occurrences now."""
    for stored in (False, True):
        rule = rule_from_dict(
            {
                "type": "WeeklyByDaysRule",
                "start_date": {
                    "value": "2026-03-05T09:00:00",
                    "kind": "floating",
                    "timezone": "UTC",
                },
                "interval": 1,
                "keep_missed": stored,
                "days_of_week": [0, 1, 2, 3, 4, 5],
            }
        )
        assert not rule.catch_up
