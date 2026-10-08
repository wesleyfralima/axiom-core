"""The commitment limit: a day's capacity (the productive day minus a
margin; today, the clock), what fills it, and the warning wherever a task
lands on a full day — plus the time a task really took, and an hourly series
never longer than its interval.

The fake clock is moved by hand; the user is in UTC, the day from 08:00 to
23:00 (15h; 13h30 with the default 10% margin), and a task lasts an hour.
"""

from datetime import UTC, date, datetime

import pytest

from a_core.exceptions import InvalidValueError, ValidationException
from b_domain.entities import User
from b_domain.entities.user import UserPrefs
from b_domain.value_objects import RecurrenceInterval, TaskId
from c_application.dtos.recurrence_dtos import RecurrenceInputDTO
from c_application.dtos.task_dtos import (
    AddSubtasksInputDTO,
    CreateTaskInputDTO,
    TaskByUserRequest,
    TaskHistoryRequest,
    TaskOutputDTO,
    UpdateTaskInputDTO,
)
from c_application.use_cases import (
    AddSubtasksUseCase,
    CompleteTaskUseCase,
    CreateTaskUseCase,
    GetTaskHistoryUseCase,
    ReportUseCase,
    SnoozeTaskUseCase,
    TodayUseCase,
    UpdateTaskUseCase,
)
from c_application.use_cases.task.capacity import available_minutes
from c_application.use_cases.task.report import ReportRequest
from c_application.use_cases.task.snooze import SnoozeTaskRequest
from c_application.use_cases.task.today import TodayRequest
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


# --- The day's capacity --------------------------------------------------------


async def test_the_productive_day_minus_its_margin() -> None:
    prefs = UserPrefs()
    assert (prefs.day_minutes, prefs.day_capacity_minutes) == (900, 810)
    late = prefs.update(day_end="1:00", day_margin=25)  # past midnight
    assert (late.day_end, late.day_minutes, late.day_capacity_minutes) == (
        "01:00",
        1020,
        765,
    )
    for margin in (4, 26):
        with pytest.raises(InvalidValueError, match="5 to 25"):
            prefs.update(day_margin=margin)
    with pytest.raises(InvalidValueError):
        prefs.update(day_start="25:00")


@pytest.mark.parametrize(
    ("now", "left"),
    [
        (_at(7), 810),  # before the day starts: all of it
        (_at(20), 162),  # 3 hours left, minus 10%
        (_at(23, 30), 0),  # over
    ],
)
async def test_today_is_the_clock(now: datetime, left: int) -> None:
    assert available_minutes(UserPrefs(), date(2026, 3, 5), now) == left
    assert available_minutes(UserPrefs(), date(2026, 3, 6), now) == 810


async def test_what_fills_a_day(
    use_case_context: UseCaseDeps, user: User, fake_clock: FakeClock
) -> None:
    await _create(
        use_case_context, user, "Late", due_date="yesterday 18:00", estimated_minutes=60
    )
    trip = await _create(
        use_case_context, user, "Trip", due_date="today 18:00", estimated_minutes=60
    )
    await AddSubtasksUseCase(
        **use_case_context
    ).execute(  # the parent covers it
        AddSubtasksInputDTO(
            user_id=str(user.id), parent_id=trip.id[:8], titles=["Pack"]
        )
    )
    await _create(  # hourly: never counts
        use_case_context,
        user,
        "Water",
        estimated_minutes=5,
        recurrence=RecurrenceInputDTO(
            frequency=RecurrenceInterval.HOURLY, start_date="today 09:00"
        ),
    )
    done = await _create(
        use_case_context, user, "Done", due_date="today 10:00", estimated_minutes=120
    )
    await CompleteTaskUseCase(**use_case_context).execute(
        TaskByUserRequest(task_id_prefix=done.id[:8], user_id=str(user.id))
    )
    await _create(
        use_case_context, user, "Tomorrow", due_date="tomorrow", estimated_minutes=90
    )

    fake_clock.set_time(_at(20))
    day = await TodayUseCase(**use_case_context).execute(
        TodayRequest(user_id=str(user.id))
    )

    assert day.load is not None
    assert (day.load.planned_minutes, day.load.available_minutes) == (120, 162)
    assert not day.load.is_full and day.load.is_today


# --- The warning ------------------------------------------------------------------


async def test_landing_on_a_full_day_warns(
    use_case_context: UseCaseDeps, user: User
) -> None:
    first = await _create(
        use_case_context, user, "Big", due_date="tomorrow", estimated_minutes=420
    )
    assert first.full_day is None

    second = await _create(
        use_case_context, user, "Bigger", due_date="tomorrow", estimated_minutes=420
    )

    assert second.full_day is not None
    assert (second.full_day.day, second.full_day.planned_minutes) == (
        date(2026, 3, 6),
        840,
    )
    assert second.full_day.available_minutes == 810


async def test_edit_snooze_and_add_to_warn_too(
    use_case_context: UseCaseDeps, user: User
) -> None:
    await _create(
        use_case_context, user, "Big", due_date="tomorrow", estimated_minutes=795
    )
    small = await _create(
        use_case_context, user, "Small", due_date="today 09:00", estimated_minutes=20
    )
    update = UpdateTaskUseCase(**use_case_context)

    renamed = await update.execute(
        UpdateTaskInputDTO(
            user_id=str(user.id), task_id_prefix=small.id[:8], title="Tiny"
        )
    )
    assert renamed.full_day is None  # not moved, not grown

    snoozed = await SnoozeTaskUseCase(**use_case_context).execute(
        SnoozeTaskRequest(user_id=str(user.id), task_id_prefix=small.id[:8])
    )
    assert snoozed.full_day is not None
    assert snoozed.full_day.planned_minutes == 815

    grown = await AddSubtasksUseCase(**use_case_context).execute(
        AddSubtasksInputDTO(
            user_id=str(user.id),
            parent_id=small.id[:8],
            titles=["One", "Two"],
            estimated_minutes=30,
        )
    )
    assert grown.full_day is not None
    assert grown.full_day.planned_minutes == 855  # 795 + its 60 now

    moved = await update.execute(
        UpdateTaskInputDTO(
            user_id=str(user.id), task_id_prefix=small.id[:8], due_date="2026-03-09"
        )
    )
    assert moved.full_day is None  # Monday is empty


async def test_the_warning_can_be_turned_off(
    use_case_context: UseCaseDeps, user: User
) -> None:
    user.preferences = user.preferences.update(full_day_warnings=False)
    await _create(
        use_case_context, user, "Big", due_date="tomorrow", estimated_minutes=780
    )
    more = await _create(
        use_case_context, user, "More", due_date="tomorrow", estimated_minutes=60
    )
    assert more.full_day is None


# --- The time it took ----------------------------------------------------------------


async def test_done_saying_how_long_it_took(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    task = await _create(
        use_case_context, user, "Call", due_date="today 09:00", estimated_minutes=60
    )

    done = await CompleteTaskUseCase(**use_case_context).execute(
        TaskByUserRequest(
            task_id_prefix=task.id[:8], user_id=str(user.id), took_minutes=10
        )
    )

    assert done.completed_task.took_minutes == 10
    async with fake_uow_factory() as uow:
        stored = await uow.tasks.get_by_id(TaskId.from_string(task.id))
    assert stored is not None and stored.average_duration_minutes == 10
    report = await ReportUseCase(**use_case_context).execute(
        ReportRequest(user_id=str(user.id))
    )
    [overall] = [a for a in report.accuracy if a.label == "all"]
    assert (overall.estimated_minutes, overall.actual_minutes) == (60, 10)


async def test_told_after_it_was_done(
    use_case_context: UseCaseDeps, user: User
) -> None:
    task = await _create(use_case_context, user, "Call", due_date="today 09:00")
    update = UpdateTaskUseCase(**use_case_context)
    with pytest.raises(ValidationException, match="only a done task"):
        await update.execute(
            UpdateTaskInputDTO(
                user_id=str(user.id), task_id_prefix=task.id[:8], took_minutes=10
            )
        )
    await CompleteTaskUseCase(**use_case_context).execute(
        TaskByUserRequest(task_id_prefix=task.id[:8], user_id=str(user.id))
    )

    told = await update.execute(
        UpdateTaskInputDTO(
            user_id=str(user.id), task_id_prefix=task.id[:8], took_minutes=25
        )
    )

    assert told.took_minutes == 25
    log = await GetTaskHistoryUseCase(**use_case_context).execute(
        TaskHistoryRequest(task_id_prefix=task.id[:8], user_id=str(user.id))
    )
    [change] = log.entries[-1].changes
    assert (change.field, change.before, change.after) == ("took", None, "25")


# --- An hourly series never longer than its interval ---------------------------------


async def test_an_hourly_series_fits_its_interval(
    use_case_context: UseCaseDeps, user: User
) -> None:
    every_two = RecurrenceInputDTO(
        frequency=RecurrenceInterval.HOURLY, interval=2, start_date="today 09:00"
    )
    with pytest.raises(ValidationException, match="every 2 hours: it can take 2h"):
        await _create(
            use_case_context, user, "Water", recurrence=every_two, estimated_minutes=180
        )
    water = await _create(
        use_case_context, user, "Water", recurrence=every_two, estimated_minutes=120
    )
    with pytest.raises(ValidationException, match="can take 2h at most"):
        await UpdateTaskUseCase(**use_case_context).execute(
            UpdateTaskInputDTO(
                user_id=str(user.id), task_id_prefix=water.id[:8], estimated_minutes=121
            )
        )
