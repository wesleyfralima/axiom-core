"""The procrastination radar: a task put off three times, or a series missed
three in a row, asks for a decision — in `today` and `wrap`.

The fake clock is moved by hand; the user is in UTC and a task lasts an
hour.
"""

from datetime import UTC, datetime

import pytest

from a_core import UniqueId
from b_domain.entities import User
from b_domain.events.task_events import TaskCancelledEvent, TaskCompletedEvent
from b_domain.value_objects import RecurrenceInterval, TaskId
from b_domain.value_objects.task_history import TaskAction
from c_application.dtos.recurrence_dtos import RecurrenceInputDTO
from c_application.dtos.task_dtos import (
    AddSubtasksInputDTO,
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
    AddSubtasksUseCase,
    CancelTaskUseCase,
    CompleteTaskUseCase,
    CreateTaskUseCase,
    SnoozeTaskUseCase,
    TodayUseCase,
    UndoPreviewUseCase,
    UndoUseCase,
    UpdateTaskUseCase,
    WrapUseCase,
)
from c_application.use_cases.task.snooze import SnoozeTaskRequest
from c_application.use_cases.task.today import TodayOutputDTO, TodayRequest
from c_application.use_cases.task.undo import UndoRequest
from c_application.use_cases.task.wrap import WrapAction, WrapRequest
from tests.conftest import FakeClock, FakeUowFactory, UseCaseDeps

pytestmark = [pytest.mark.asyncio, pytest.mark.uc]


def _at(day: int, hour: int = 7) -> datetime:
    return datetime(2026, 3, day, hour, 0, tzinfo=UTC)


@pytest.fixture
async def user(fake_uow_factory: FakeUowFactory, fake_clock: FakeClock) -> User:
    created = User.create(username="wesley", email="wesley@test.com")
    await fake_uow_factory().users.add(created)
    fake_clock.set_time(_at(5))
    return created


async def _create(
    deps: UseCaseDeps, user: User, title: str, **kwargs: object
) -> TaskOutputDTO:
    return await CreateTaskUseCase(**deps).execute(
        CreateTaskInputDTO(user_id=str(user.id), title=title, **kwargs)  # type: ignore[arg-type]
    )


async def _snooze(deps: UseCaseDeps, user: User, task: TaskOutputDTO) -> None:
    await SnoozeTaskUseCase(**deps).execute(
        SnoozeTaskRequest(user_id=str(user.id), task_id_prefix=task.id[:8], minutes=30)
    )


async def _today(deps: UseCaseDeps, user: User) -> TodayOutputDTO:
    return await TodayUseCase(**deps).execute(TodayRequest(user_id=str(user.id)))


async def _close(
    deps: UseCaseDeps,
    user: User,
    uow_factory: FakeUowFactory,
    task_id: str,
    done: bool,
) -> str:
    """Complete or skip an occurrence, and make the next as the relay does;
    the next one's ID."""
    if done:
        await CompleteTaskUseCase(**deps).execute(
            TaskByUserRequest(task_id_prefix=task_id[:8], user_id=str(user.id))
        )
    else:
        await CancelTaskUseCase(**deps).execute(
            CancelTaskInputDTO(task_id_prefix=task_id[:8], user_id=str(user.id))
        )
    action = TaskAction.COMPLETED if done else TaskAction.CANCELLED
    async with uow_factory() as uow:
        [entry] = [
            e
            for e in await uow.task_history.recent(user.id)
            if e.action == action and str(e.task_id) == task_id
        ]
        closed = await uow.tasks.get_by_id(TaskId.from_string(task_id))
    assert closed is not None
    event: TaskCompletedEvent | TaskCancelledEvent = (
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
        if done
        else TaskCancelledEvent(
            id=UniqueId(entry.entry_id),
            occurred_at=entry.occurred_at,
            task_id=closed.id,
            user_id=user.id,
        )
    )
    await CreateRecurringTaskHandler(uow_factory()).handle(event)
    async with uow_factory() as uow:
        made = [
            t
            for t in uow.tasks.tasks.values()
            if t.series_id == closed.series_id and not t.status.is_closed
        ]
    return str(made[0].id)


# --- Put off ------------------------------------------------------------------


async def test_put_off_three_times_is_flagged(
    use_case_context: UseCaseDeps, user: User
) -> None:
    bill = await _create(use_case_context, user, "Pay the bill", due_date="today 08:00")
    for _ in range(2):
        await _snooze(use_case_context, user, bill)
    assert (await _today(use_case_context, user)).radar == []

    # An edit moving it later counts too
    await UpdateTaskUseCase(**use_case_context).execute(
        UpdateTaskInputDTO(
            user_id=str(user.id), task_id_prefix=bill.id[:8], due_date="today 20:00"
        )
    )

    [flag] = (await _today(use_case_context, user)).radar
    assert (flag.title, flag.postponed, flag.missed_in_row) == ("Pay the bill", 3, 0)
    [item] = (
        await WrapUseCase(**use_case_context).execute(WrapRequest(user_id=str(user.id)))
    ).left
    assert item.radar is not None and item.radar.postponed == 3
    assert WrapAction.SPLIT in item.actions


async def test_earlier_undone_or_along_does_not_count(
    use_case_context: UseCaseDeps, user: User
) -> None:
    trip = await _create(use_case_context, user, "Trip", due_date="today 18:00")
    added = await AddSubtasksUseCase(**use_case_context).execute(
        AddSubtasksInputDTO(
            user_id=str(user.id), parent_id=trip.id[:8], titles=["Pack"]
        )
    )
    update = UpdateTaskUseCase(**use_case_context)
    await update.execute(  # earlier: not put off
        UpdateTaskInputDTO(
            user_id=str(user.id), task_id_prefix=trip.id[:8], due_date="today 12:00"
        )
    )
    for _ in range(2):
        await _snooze(use_case_context, user, trip)
    await _snooze(use_case_context, user, trip)
    preview = await UndoPreviewUseCase(**use_case_context).execute(
        UndoRequest(user_id=str(user.id))
    )
    await UndoUseCase(**use_case_context).execute(
        UndoRequest(user_id=str(user.id), entry_id=preview.entry_id)
    )

    # Trip: two snoozes left; Pack only moved along with it
    assert (await _today(use_case_context, user)).radar == []
    assert added.subtasks[0].title == "Pack"


async def test_the_warnings_can_be_turned_off(
    use_case_context: UseCaseDeps, user: User
) -> None:
    bill = await _create(use_case_context, user, "Pay the bill", due_date="today 08:00")
    for _ in range(3):
        await _snooze(use_case_context, user, bill)
    user.preferences = user.preferences.update(postpone_warnings=False)

    assert (await _today(use_case_context, user)).radar == []
    [item] = (
        await WrapUseCase(**use_case_context).execute(WrapRequest(user_id=str(user.id)))
    ).left
    assert item.radar is None and WrapAction.SPLIT not in item.actions


# --- Missed in a row -----------------------------------------------------------


def _gym() -> RecurrenceInputDTO:
    return RecurrenceInputDTO(
        frequency=RecurrenceInterval.DAILY, start_date="2026-03-01 18:00"
    )


async def test_skipped_three_in_a_row(
    use_case_context: UseCaseDeps,
    user: User,
    fake_uow_factory: FakeUowFactory,
    fake_clock: FakeClock,
) -> None:
    fake_clock.set_time(_at(1))
    gym = await _create(use_case_context, user, "Gym", recurrence=_gym())
    current: str = gym.id
    for day in (1, 2):  # skipped on its day, each
        fake_clock.set_time(_at(day, 20))
        current = await _close(
            use_case_context, user, fake_uow_factory, current, done=False
        )

    fake_clock.set_time(_at(4))  # the 3rd's day is gone too
    [flag] = (await _today(use_case_context, user)).radar
    assert (flag.title, flag.missed_in_row) == ("Gym", 3)


async def test_a_habit_left_open_counts_the_days_gone(
    use_case_context: UseCaseDeps,
    user: User,
    fake_uow_factory: FakeUowFactory,
    fake_clock: FakeClock,
) -> None:
    fake_clock.set_time(_at(1, 20))
    gym = await _create(use_case_context, user, "Gym", recurrence=_gym())
    await _close(use_case_context, user, fake_uow_factory, gym.id, done=True)

    fake_clock.set_time(_at(4))  # the 2nd and 3rd gone, the 4th still ahead
    assert (await _today(use_case_context, user)).radar == []
    fake_clock.set_time(_at(5))  # the 2nd, 3rd and 4th gone
    [flag] = (await _today(use_case_context, user)).radar
    assert flag.missed_in_row == 3


async def test_a_habit_done_late_counts_the_ones_it_skipped(
    use_case_context: UseCaseDeps,
    user: User,
    fake_uow_factory: FakeUowFactory,
    fake_clock: FakeClock,
) -> None:
    """Done on the 1st; the 2nd skipped on the 5th: the 3rd and 4th were
    never made — with the 2nd, three in a row."""
    fake_clock.set_time(_at(1, 20))
    gym = await _create(use_case_context, user, "Gym", recurrence=_gym())
    second = await _close(use_case_context, user, fake_uow_factory, gym.id, done=True)
    fake_clock.set_time(_at(5, 12))
    await _close(use_case_context, user, fake_uow_factory, second, done=False)

    [flag] = (await _today(use_case_context, user)).radar
    assert flag.missed_in_row == 3


async def test_done_breaks_the_run(
    use_case_context: UseCaseDeps,
    user: User,
    fake_uow_factory: FakeUowFactory,
    fake_clock: FakeClock,
) -> None:
    fake_clock.set_time(_at(1, 20))
    gym = await _create(use_case_context, user, "Gym", recurrence=_gym())
    current = await _close(use_case_context, user, fake_uow_factory, gym.id, done=False)
    fake_clock.set_time(_at(2, 20))
    current = await _close(use_case_context, user, fake_uow_factory, current, done=True)
    fake_clock.set_time(_at(4))
    assert (await _today(use_case_context, user)).radar == []
