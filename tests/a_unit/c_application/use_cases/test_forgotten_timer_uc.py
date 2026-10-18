"""The forgotten timer (product Backlog 09, Part 3): one running past the
end of the productive day it started in is warned — with the user's last
change that day, a hint of when they stopped — and never cut.

The user is in UTC, the day from 08:00 to 23:00 (the defaults).
"""

from datetime import UTC, datetime

import pytest

from b_domain.entities import User
from b_domain.exceptions import TimerRunningError
from c_application.dtos.task_dtos import CreateTaskInputDTO, TaskOutputDTO
from c_application.use_cases import (
    CreateTaskUseCase,
    StartTaskUseCase,
    TodayUseCase,
    WrapUseCase,
)
from c_application.use_cases.task.timer import TimerRequest
from c_application.use_cases.task.today import TodayRequest
from c_application.use_cases.task.wrap import WrapAction, WrapRequest
from tests.conftest import FakeClock, FakeUowFactory, UseCaseDeps

pytestmark = [pytest.mark.asyncio, pytest.mark.uc]


def _at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 3, day, hour, minute, tzinfo=UTC)


@pytest.fixture
async def user(fake_uow_factory: FakeUowFactory, fake_clock: FakeClock) -> User:
    created = User.create(username="wesley", email="wesley@test.com")
    await fake_uow_factory().users.add(created)
    fake_clock.set_time(_at(4, 20, 10))
    return created


async def _create(
    deps: UseCaseDeps, user: User, title: str, **kw: object
) -> TaskOutputDTO:
    return await CreateTaskUseCase(**deps).execute(
        CreateTaskInputDTO(user_id=str(user.id), title=title, **kw)  # type: ignore[arg-type]
    )


async def _start(deps: UseCaseDeps, user: User, task: TaskOutputDTO) -> None:
    await StartTaskUseCase(**deps).execute(
        TimerRequest(task_id_prefix=task.id, user_id=str(user.id))
    )


async def test_a_timer_left_running_overnight_is_warned(
    use_case_context: UseCaseDeps, user: User, fake_clock: FakeClock
) -> None:
    """Started at 20:10, a task added at 22:40, then bed; noon the next
    day: forgotten, and 22:40 is when they were still at it."""
    bank = await _create(use_case_context, user, "Bank", due_date="2026-03-05 18:00")
    await _start(use_case_context, user, bank)
    fake_clock.set_time(_at(4, 22, 40))
    await _create(use_case_context, user, "Groceries")
    fake_clock.set_time(_at(5, 12))

    day = await TodayUseCase(**use_case_context).execute(
        TodayRequest(user_id=str(user.id))
    )

    assert day.timer is not None
    assert (day.timer.title, day.timer.forgotten) == ("Bank", True)
    assert (day.timer.since, day.timer.last_change) == (_at(4, 20, 10), _at(4, 22, 40))
    assert day.timer.minutes == 15 * 60 + 50

    # A start is refused, saying the same
    other = await _create(use_case_context, user, "Other")
    with pytest.raises(TimerRunningError) as refused:
        await _start(use_case_context, user, other)
    assert refused.value.forgotten and refused.value.last_change == _at(4, 22, 40)

    # wrap offers to pause or discard it on its task
    wrap = await WrapUseCase(**use_case_context).execute(
        WrapRequest(user_id=str(user.id))
    )
    [item] = [i for i in wrap.left if i.task.title == "Bank"]
    assert WrapAction.PAUSE_TIMER in item.actions
    assert WrapAction.DISCARD_TIMER in item.actions
    assert wrap.timer is not None and wrap.timer.forgotten


async def test_a_timer_within_its_day_is_not_forgotten(
    use_case_context: UseCaseDeps, user: User, fake_clock: FakeClock
) -> None:
    task = await _create(use_case_context, user, "Write")
    await _start(use_case_context, user, task)
    fake_clock.set_time(_at(4, 22, 59))

    day = await TodayUseCase(**use_case_context).execute(
        TodayRequest(user_id=str(user.id))
    )

    assert day.timer is not None and not day.timer.forgotten
    assert day.timer.last_change is None


async def test_nothing_after_the_start_suggests_no_time(
    use_case_context: UseCaseDeps, user: User, fake_clock: FakeClock
) -> None:
    task = await _create(use_case_context, user, "Write")
    await _start(use_case_context, user, task)
    fake_clock.set_time(_at(5, 9))

    day = await TodayUseCase(**use_case_context).execute(
        TodayRequest(user_id=str(user.id))
    )

    assert day.timer is not None and day.timer.forgotten
    assert day.timer.last_change is None


async def test_a_day_ending_past_midnight(
    use_case_context: UseCaseDeps, user: User, fake_clock: FakeClock
) -> None:
    """The day ends at 01:00: a timer started at 00:30 is the day before's,
    forgotten from 01:00 on."""
    user.preferences = user.preferences.update(day_end="01:00")
    task = await _create(use_case_context, user, "Late work")
    fake_clock.set_time(_at(5, 0, 30))
    await _start(use_case_context, user, task)
    today = TodayUseCase(**use_case_context)

    fake_clock.set_time(_at(5, 0, 50))
    within = await today.execute(TodayRequest(user_id=str(user.id)))
    fake_clock.set_time(_at(5, 1, 10))
    past = await today.execute(TodayRequest(user_id=str(user.id)))

    assert within.timer is not None and not within.timer.forgotten
    assert past.timer is not None and past.timer.forgotten


async def test_no_timer_no_warning(use_case_context: UseCaseDeps, user: User) -> None:
    day = await TodayUseCase(**use_case_context).execute(
        TodayRequest(user_id=str(user.id))
    )
    assert day.timer is None
