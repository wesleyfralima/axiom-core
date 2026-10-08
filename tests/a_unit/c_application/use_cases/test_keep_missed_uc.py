"""A series that keeps its missed occurrences (a bill) or skips them (a
habit, the default).

The fake clock is moved to Thursday 2026-03-05, 07:00 by hand; the user is
in UTC and a task lasts an hour.
"""

from datetime import UTC, datetime

import pytest

from a_core import UniqueId
from a_core.exceptions import ValidationException
from b_domain.entities import User
from b_domain.events.task_events import TaskCompletedEvent
from b_domain.ports.repositories.filters import TaskFilter
from b_domain.value_objects import RecurrenceInterval, TaskId
from b_domain.value_objects.recurrences._serial import rule_from_dict, rule_to_dict
from b_domain.value_objects.task_history import TaskAction
from c_application.dtos.recurrence_dtos import RecurrenceInputDTO
from c_application.dtos.task_dtos import (
    CreateTaskInputDTO,
    TaskByUserRequest,
    TaskOutputDTO,
    UpdateTaskInputDTO,
)
from c_application.handlers.task_handlers.create_recurring_task_handler import (
    CreateRecurringTaskHandler,
)
from c_application.use_cases import (
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
    deps: UseCaseDeps, user: User, start: str, keep_missed: bool = False
) -> TaskOutputDTO:
    return await CreateTaskUseCase(**deps).execute(
        CreateTaskInputDTO(
            user_id=str(user.id),
            title="Rent",
            recurrence=RecurrenceInputDTO(
                frequency=RecurrenceInterval.DAILY,
                start_date=start,
                keep_missed=keep_missed,
            ),
        )
    )


async def _done_and_next(
    deps: UseCaseDeps, user: User, uow_factory: FakeUowFactory, task: TaskOutputDTO
) -> datetime:
    """Complete it, run the handler as the relay does; the next one's due."""
    await CompleteTaskUseCase(**deps).execute(
        TaskByUserRequest(task_id_prefix=task.id[:8], user_id=str(user.id))
    )
    async with uow_factory() as uow:
        [entry] = [
            e
            for e in await uow.task_history.recent(user.id)
            if e.action == TaskAction.COMPLETED and str(e.task_id) == task.id
        ]
        closed = await uow.tasks.get_by_id(TaskId.from_string(task.id))
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
        )
    )
    async with uow_factory() as uow:
        open_ones = [
            t
            for t in await uow.tasks.list(TaskFilter(user_id=user.id, in_series=True))
            if not t.status.is_closed
        ]
    [following] = open_ones
    assert following.due_date is not None
    return following.due_date.value


async def test_created_as_a_bill_it_says_so(
    use_case_context: UseCaseDeps, user: User
) -> None:
    rent = await _daily(use_case_context, user, "today 09:00", keep_missed=True)
    assert rent.recurrence is not None and rent.recurrence.keep_missed
    assert rent.recurrence_display == "Every day, keeping the missed ones."
    habit = await _daily(use_case_context, user, "today 10:00")
    assert habit.recurrence is not None and not habit.recurrence.keep_missed


@pytest.mark.parametrize(
    ("keep_missed", "next_due"),
    [
        (False, datetime(2026, 3, 5, 9, 0)),  # a habit: the first still on time
        (True, datetime(2026, 3, 3, 9, 0)),  # a bill: the one after, late or not
    ],
)
async def test_done_late_the_next_one(
    use_case_context: UseCaseDeps,
    user: User,
    fake_uow_factory: FakeUowFactory,
    keep_missed: bool,
    next_due: datetime,
) -> None:
    rent = await _daily(use_case_context, user, "2026-03-02 09:00", keep_missed)
    assert rent.due_date == datetime(2026, 3, 2, 9, 0)

    following = await _done_and_next(use_case_context, user, fake_uow_factory, rent)

    assert following == next_due


async def test_a_snoozed_bill_lands_anywhere_and_eats_no_one(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    rent = await _daily(use_case_context, user, "today 06:30", keep_missed=True)

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

    bill = await update.execute(
        UpdateTaskInputDTO(
            user_id=str(user.id), task_id_prefix=rent.id[:8], keep_missed=True
        )
    )
    assert bill.recurrence is not None and bill.recurrence.keep_missed

    weekly = await update.execute(
        UpdateTaskInputDTO(
            user_id=str(user.id),
            task_id_prefix=rent.id[:8],
            recurrence=RecurrenceInputDTO(frequency=RecurrenceInterval.WEEKLY),
        )
    )
    assert weekly.recurrence is not None and weekly.recurrence.keep_missed

    habit = await update.execute(
        UpdateTaskInputDTO(
            user_id=str(user.id), task_id_prefix=rent.id[:8], keep_missed=False
        )
    )
    assert habit.recurrence is not None and not habit.recurrence.keep_missed


async def test_only_a_recurring_task(use_case_context: UseCaseDeps, user: User) -> None:
    once = await CreateTaskUseCase(**use_case_context).execute(
        CreateTaskInputDTO(user_id=str(user.id), title="Once", due_date="today 09:00")
    )
    with pytest.raises(ValidationException, match="does not repeat"):
        await UpdateTaskUseCase(**use_case_context).execute(
            UpdateTaskInputDTO(
                user_id=str(user.id), task_id_prefix=once.id[:8], keep_missed=True
            )
        )


async def test_wrap_offers_tomorrow_to_a_daily_bill(
    use_case_context: UseCaseDeps, user: User
) -> None:
    await _daily(use_case_context, user, "today 06:00", keep_missed=True)
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
        keep_missed=True,
    )
    assert rule_from_dict(rule_to_dict(rule)).keep_missed
