"""The user's business days, loaded when a rule needs them.

A rule that counts business days (``BusinessDayRule``) does not store what a
business day is: that is the user's calendar (work days, their region's
holidays, their own days), which can change at any time. Whoever computes
occurrences hands it over first — ``use_work_calendar`` — and it is only
loaded when some task needs it.
"""

from collections.abc import Iterable, Mapping
from datetime import date

from b_domain.entities import Task, UserPrefs
from b_domain.ports.unit_of_work import UnitOfWork
from b_domain.value_objects import UserId
from b_domain.value_objects.work_calendar import (
    HolidayLookup,
    WorkCalendar,
    no_holidays,
)


async def load_work_calendar(
    uow: UnitOfWork, user_id: UserId, prefs: UserPrefs
) -> WorkCalendar:
    """The user's calendar: their preferences, region and own days.

    Args:
        uow (UnitOfWork): An open unit of work.
        user_id (UserId): The user.
        prefs (UserPrefs): Their preferences (work days, region).

    Returns:
        WorkCalendar: What a business day is for them.
    """
    return WorkCalendar(
        work_days=prefs.work_weekdays,
        region=prefs.holiday_region,
        holidays=region_holidays(uow, prefs.holiday_region),
        days=tuple(await uow.calendar_days.list_by_user(user_id)),
        skipped=prefs.skipped_holiday_names,
    )


def region_holidays(uow: UnitOfWork, region: str) -> HolidayLookup:
    """A region's holidays by year, from the unit of work's provider."""
    if not region:
        return no_holidays

    def lookup(year: int) -> Mapping[date, str]:
        return uow.holidays.holidays(region, year)

    return lookup


async def use_work_calendar(
    uow: UnitOfWork, user_id: UserId, prefs: UserPrefs, tasks: Iterable[Task]
) -> WorkCalendar | None:
    """Give the tasks whose rule counts business days the user's calendar.

    Nothing is loaded when no task needs it.

    Args:
        uow (UnitOfWork): An open unit of work.
        user_id (UserId): The tasks' owner.
        prefs (UserPrefs): Their preferences.
        tasks (Iterable[Task]): The tasks about to have occurrences computed.

    Returns:
        WorkCalendar | None: The calendar, if it was loaded.
    """
    needing: list[Task] = [
        t for t in tasks if t.recurrence is not None and t.recurrence.uses_business_days
    ]
    if not needing:
        return None
    calendar: WorkCalendar = await load_work_calendar(uow, user_id, prefs)
    for task in needing:
        task.use_business_days(calendar.is_business_day)
    return calendar
