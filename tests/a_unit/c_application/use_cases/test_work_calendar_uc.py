"""The user's business days: their own days, their region, and the rules that
count business days.

The fake clock says 2026-03-05 12:00 UTC (a Thursday); the user is in UTC.
In April 2026, the 3rd is Good Friday and the 4th a Saturday; 1 May is
Labour Day.
"""

from datetime import date, datetime

import pytest

from a_core import EntityNotFound
from a_core.exceptions import InvalidValueError
from b_domain.entities import Task, User
from b_domain.events.task_events import TaskCompletedEvent
from b_domain.exceptions import UnknownHolidayRegionError
from b_domain.value_objects import RecurrenceInterval
from b_domain.value_objects.work_calendar import CalendarDay, CalendarDayKind
from c_application.dtos.recurrence_dtos import RecurrenceInputDTO
from c_application.dtos.task_dtos import (
    CreateTaskInputDTO,
    GetTaskRequest,
    ListTasksRequest,
    TaskOutputDTO,
    UpdateTaskInputDTO,
)
from c_application.dtos.user_dtos import UserPrefsInputDTO
from c_application.handlers.task_handlers.create_recurring_task_handler import (
    CreateRecurringTaskHandler,
)
from c_application.use_cases import (
    CreateTaskUseCase,
    GetTaskUseCase,
    ListTasksUseCase,
    UpdateTaskUseCase,
)
from c_application.use_cases.user.prepare_prefs import (
    PrepareUserPreferencesInputDTO,
    PrepareUserPreferencesUseCase,
)
from c_application.use_cases.user.update_prefs import (
    UpdateUserPreferencesInputDTO,
    UpdateUserPreferencesUseCase,
)
from c_application.use_cases.work_calendar import (
    ListHolidayRegionsInputDTO,
    ListHolidayRegionsUseCase,
    RemoveCalendarDayInputDTO,
    RemoveCalendarDayUseCase,
    SetCalendarDayInputDTO,
    SetCalendarDayUseCase,
    ShowWorkCalendarInputDTO,
    ShowWorkCalendarUseCase,
)
from tests.conftest import FakeUowFactory, UseCaseDeps

pytestmark = [pytest.mark.asyncio, pytest.mark.uc]

GOOD_FRIDAY = date(2026, 4, 3)
LABOUR_DAY = date(2026, 5, 1)


@pytest.fixture
async def user(fake_uow_factory: FakeUowFactory) -> User:
    created = User.create(username="wesley", email="wesley@test.com")
    uow = fake_uow_factory()
    await uow.users.add(created)
    uow.holidays.by_region["BR"] = {
        GOOD_FRIDAY: "Good Friday",
        LABOUR_DAY: "Labour Day",
        date(2026, 11, 15): "Republic Day",  # a Sunday
    }
    return created


def _in_brazil(user: User) -> None:
    user.preferences = user.preferences.update(holiday_region="BR")


async def _set(deps: UseCaseDeps, user: User, typed: str, kind: str, **kw: object):  # type: ignore[no-untyped-def]
    return await SetCalendarDayUseCase(**deps).execute(
        SetCalendarDayInputDTO(user_id=str(user.id), date=typed, kind=kind, **kw)  # type: ignore[arg-type]
    )


async def _fifth_business_day(deps: UseCaseDeps, user: User) -> TaskOutputDTO:
    return await CreateTaskUseCase(**deps).execute(
        CreateTaskInputDTO(
            user_id=str(user.id),
            title="Pay the team",
            recurrence=RecurrenceInputDTO(
                frequency=RecurrenceInterval.MONTHLY,
                start_date="2026-04-01 09:00",
                nth_business_day=5,
            ),
        )
    )


def _day(output: TaskOutputDTO) -> date:
    assert output.due_date is not None
    return output.due_date.date()


# ---------------------------------------------------------------- own days


async def test_a_day_off_once(use_case_context: UseCaseDeps, user: User) -> None:
    result = await _set(
        use_case_context, user, "12-24", "day_off", name="Christmas Eve"
    )

    assert result.action == "added"
    assert result.day.date == "2026-12-24"
    assert result.day.name == "Christmas Eve"
    assert result.day.kind == "day_off"
    assert not result.day.yearly
    assert not result.day.is_business_day
    assert not result.changes_nothing


async def test_a_day_off_every_year(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    await _set(use_case_context, user, "2026-01-25", "day_off", yearly=True)

    days = await fake_uow_factory().calendar_days.list_by_user(user.id)
    assert days == [
        CalendarDay(day=date(2026, 1, 25), kind=CalendarDayKind.DAY_OFF, yearly=True)
    ]
    shown = await ShowWorkCalendarUseCase(**use_case_context).execute(
        ShowWorkCalendarInputDTO(user_id=str(user.id))
    )
    # Already past this year: next year's
    assert [d.date for d in shown.days] == ["2027-01-25"]


async def test_setting_a_date_again_replaces_it(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    await _set(use_case_context, user, "2026-04-02", "day_off")

    result = await _set(use_case_context, user, "2026-04-02", "workday")

    assert result.action == "replaced"
    assert not result.changes_nothing  # it was a day off
    days = await fake_uow_factory().calendar_days.list_by_user(user.id)
    assert [d.kind for d in days] == [CalendarDayKind.WORKDAY]


async def test_a_day_off_on_a_sunday_changes_nothing(
    use_case_context: UseCaseDeps, user: User
) -> None:
    result = await _set(use_case_context, user, "2026-03-08", "day_off")
    assert result.changes_nothing


async def test_an_unknown_kind_is_refused(
    use_case_context: UseCaseDeps, user: User
) -> None:
    with pytest.raises(InvalidValueError, match="kind of day"):
        await _set(use_case_context, user, "2026-04-02", "holiday")


async def test_removing_a_day(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    await _set(use_case_context, user, "2026-01-25", "day_off", yearly=True)
    await _set(use_case_context, user, "2027-01-25", "workday")

    remove = RemoveCalendarDayUseCase(**use_case_context)
    # The one-off first; then the yearly one, by any year's date
    first = await remove.execute(
        RemoveCalendarDayInputDTO(user_id=str(user.id), date="2027-01-25")
    )
    second = await remove.execute(
        RemoveCalendarDayInputDTO(user_id=str(user.id), date="01-25")
    )

    assert (first.action, first.day.kind, first.day.yearly) == (
        "removed",
        "workday",
        False,
    )
    assert second.day.yearly
    assert await fake_uow_factory().calendar_days.list_by_user(user.id) == []
    with pytest.raises(EntityNotFound):
        await remove.execute(
            RemoveCalendarDayInputDTO(user_id=str(user.id), date="01-25")
        )


async def test_removing_the_yearly_one_by_name(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    await _set(use_case_context, user, "2026-12-24", "day_off", yearly=True)
    await _set(use_case_context, user, "2026-12-24", "workday")

    await RemoveCalendarDayUseCase(**use_case_context).execute(
        RemoveCalendarDayInputDTO(user_id=str(user.id), date="12-24", yearly=True)
    )

    days = await fake_uow_factory().calendar_days.list_by_user(user.id)
    assert [d.yearly for d in days] == [False]


# ---------------------------------------------------------------- the calendar


async def test_the_calendar_lists_holidays_and_own_days(
    use_case_context: UseCaseDeps, user: User
) -> None:
    _in_brazil(user)
    await _set(use_case_context, user, "2026-04-03", "workday")
    await _set(use_case_context, user, "2026-04-20", "day_off", name="Bridge")

    shown = await ShowWorkCalendarUseCase(**use_case_context).execute(
        ShowWorkCalendarInputDTO(user_id=str(user.id), ahead="2026-05-31")
    )

    assert (shown.work_days, shown.holiday_region) == ("mon,tue,wed,thu,fri", "BR")
    assert (shown.start, shown.until) == ("2026-03-05", "2026-05-31")
    assert shown.suggested_region is None
    assert [(d.date, d.source, d.name, d.is_business_day) for d in shown.days] == [
        ("2026-04-03", "yours", "Good Friday", True),
        ("2026-04-20", "yours", "Bridge", False),
        ("2026-05-01", "holiday", "Labour Day", False),
    ]
    assert shown.days[0].holiday == "Good Friday"


async def test_a_holiday_on_a_day_off_is_shown_as_it_is(
    use_case_context: UseCaseDeps, user: User
) -> None:
    _in_brazil(user)
    shown = await ShowWorkCalendarUseCase(**use_case_context).execute(
        ShowWorkCalendarInputDTO(user_id=str(user.id))
    )
    assert [d.date for d in shown.days][-1] == "2026-11-15"
    assert not shown.days[-1].is_business_day


async def test_without_a_region_the_time_zone_suggests_one(
    use_case_context: UseCaseDeps, user: User
) -> None:
    user.preferences = user.preferences.update(timezone="America/Sao_Paulo")
    shown = await ShowWorkCalendarUseCase(**use_case_context).execute(
        ShowWorkCalendarInputDTO(user_id=str(user.id))
    )
    assert shown.suggested_region == "BR"
    assert shown.days == []


async def test_the_calendar_looks_ten_years_ahead_at_most(
    use_case_context: UseCaseDeps, user: User
) -> None:
    with pytest.raises(InvalidValueError, match="ten years"):
        await ShowWorkCalendarUseCase(**use_case_context).execute(
            ShowWorkCalendarInputDTO(user_id=str(user.id), ahead="2040-01-01")
        )


# ---------------------------------------------------------------- preferences


async def test_a_region_must_be_known(
    use_case_context: UseCaseDeps, user: User
) -> None:
    update = UpdateUserPreferencesUseCase(**use_case_context)

    with pytest.raises(UnknownHolidayRegionError, match="No holidays known"):
        await update.execute(
            UpdateUserPreferencesInputDTO(
                username="wesley",
                preferences=UserPrefsInputDTO(holiday_region="XX"),
            )
        )
    done = await update.execute(
        UpdateUserPreferencesInputDTO(
            username="wesley",
            preferences=UserPrefsInputDTO(holiday_region="br", work_days="mon-sat"),
        )
    )
    assert done.preferences.holiday_region == "BR"
    assert done.preferences.work_days == "mon,tue,wed,thu,fri,sat"


async def test_preparing_the_preferences_suggests_a_region(
    use_case_context: UseCaseDeps, user: User
) -> None:
    prepared = await PrepareUserPreferencesUseCase(**use_case_context).execute(
        PrepareUserPreferencesInputDTO(username="wesley", timezone="America/Sao_Paulo")
    )
    assert prepared.suggested_holiday_region == "BR"

    _in_brazil(user)
    prepared = await PrepareUserPreferencesUseCase(**use_case_context).execute(
        PrepareUserPreferencesInputDTO(username="wesley", timezone="America/Sao_Paulo")
    )
    assert prepared.suggested_holiday_region is None


async def test_an_unknown_region_suggests_close_ones(
    use_case_context: UseCaseDeps, user: User
) -> None:
    update = UpdateUserPreferencesUseCase(**use_case_context)

    for typed, suggested in [("Brasil", "BR (Brazil)"), ("br-paulo", "BR-SP")]:
        with pytest.raises(UnknownHolidayRegionError) as caught:
            await update.execute(
                UpdateUserPreferencesInputDTO(
                    username="wesley",
                    preferences=UserPrefsInputDTO(holiday_region=typed),
                )
            )
        assert f"Did you mean {suggested}" in str(caught.value)


# ---------------------------------------------------------------- regions


async def _regions(deps: UseCaseDeps, user: User, query: str | None = None):  # type: ignore[no-untyped-def]
    return await ListHolidayRegionsUseCase(**deps).execute(
        ListHolidayRegionsInputDTO(user_id=str(user.id), query=query)
    )


async def test_every_country(use_case_context: UseCaseDeps, user: User) -> None:
    _in_brazil(user)
    listed = await _regions(use_case_context, user)

    assert [r.code for r in listed.regions] == ["BR", "PT", "US"]
    assert listed.country is None
    assert listed.current_region == "BR"


async def test_a_countrys_subdivisions(
    use_case_context: UseCaseDeps, user: User
) -> None:
    listed = await _regions(use_case_context, user, "br")

    assert listed.country is not None
    assert (listed.country.code, listed.country.name) == ("BR", "Brazil")
    assert [(r.code, r.name) for r in listed.regions] == [
        ("BR-RJ", "Rio de Janeiro"),
        ("BR-SP", "São Paulo"),
    ]


@pytest.mark.parametrize(
    ("query", "found"),
    [
        ("port", ["PT"]),  # part of the name
        ("united", ["US"]),
        ("Brasil", ["BR"]),  # close to the name
        ("BR-SP", ["BR-SP"]),
        ("br-sao", ["BR-SP"]),  # accents never matter
        ("br-", ["BR-RJ", "BR-SP"]),
        ("atlantis", []),
    ],
)
async def test_searching_regions(
    use_case_context: UseCaseDeps, user: User, query: str, found: list[str]
) -> None:
    listed = await _regions(use_case_context, user, query)

    assert listed.country is None
    assert [r.code for r in listed.regions] == found


# ---------------------------------------------------------------- the rule


async def test_the_nth_business_day_skips_the_users_holidays(
    use_case_context: UseCaseDeps, user: User
) -> None:
    assert _day(await _fifth_business_day(use_case_context, user)) == date(2026, 4, 7)

    _in_brazil(user)
    assert _day(await _fifth_business_day(use_case_context, user)) == date(2026, 4, 8)


async def test_the_nth_business_day_counts_own_working_days(
    use_case_context: UseCaseDeps, user: User
) -> None:
    _in_brazil(user)
    await _set(use_case_context, user, "2026-04-04", "workday")  # a Saturday

    assert _day(await _fifth_business_day(use_case_context, user)) == date(2026, 4, 7)


async def test_lists_and_details_project_with_the_users_calendar(
    use_case_context: UseCaseDeps, user: User
) -> None:
    _in_brazil(user)
    created = await _fifth_business_day(use_case_context, user)

    listed = await ListTasksUseCase(**use_case_context).execute(
        ListTasksRequest(user_id=str(user.id), ahead="2026-05-31")
    )
    shown = await GetTaskUseCase(**use_case_context).execute(
        GetTaskRequest(
            user_id=str(user.id), task_id_prefix=created.id[:8], ahead="2026-05-31"
        )
    )

    # May: 1 is Labour Day, so the 5th business day is the 8th (not the 7th)
    assert [_day(p) for p in listed.projected] == [date(2026, 5, 8)]
    assert [o.date() for o in shown.next_occurrences] == [datetime(2026, 5, 8).date()]


async def test_an_edit_to_the_nth_business_day_uses_the_calendar(
    use_case_context: UseCaseDeps, user: User
) -> None:
    _in_brazil(user)
    created = await CreateTaskUseCase(**use_case_context).execute(
        CreateTaskInputDTO(user_id=str(user.id), title="Report")
    )

    edited = await UpdateTaskUseCase(**use_case_context).execute(
        UpdateTaskInputDTO(
            user_id=str(user.id),
            task_id_prefix=created.id[:8],
            recurrence=RecurrenceInputDTO(
                frequency=RecurrenceInterval.MONTHLY,
                start_date="2026-04-01 09:00",
                nth_business_day=5,
            ),
        )
    )

    assert _day(edited) == date(2026, 4, 8)


async def test_the_next_occurrence_skips_the_users_holidays(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    _in_brazil(user)
    created = await _fifth_business_day(use_case_context, user)
    task: Task = next(iter(fake_uow_factory().tasks.tasks.values()))

    await CreateRecurringTaskHandler(fake_uow_factory()).handle(
        TaskCompletedEvent(
            task_id=task.id,
            user_id=task.user_id,
            estimated_minutes=30,
            actual_minutes=0,
            energy_level_used=task.required_energy_level,
            task_complexity=task.complexity,
            occurred_at=datetime(2026, 4, 8, 10, 0),
        )
    )

    tasks = fake_uow_factory().tasks.tasks.values()
    following = [t for t in tasks if str(t.id) != created.id]
    assert len(following) == 1
    assert following[0].due_date is not None
    assert following[0].due_date.value.date() == date(2026, 5, 8)
