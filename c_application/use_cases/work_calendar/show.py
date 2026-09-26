from dataclasses import dataclass
from datetime import date, timedelta

from a_core import DTO
from a_core.exceptions import InvalidValueError
from b_domain.entities import User
from b_domain.ports.use_case import UseCase
from b_domain.value_objects.work_calendar import CalendarDay, WorkCalendar
from c_application.dtos.calendar_dtos import (
    CalendarDayOutputDTO,
    WorkCalendarOutputDTO,
)
from c_application.use_cases.context._common import load_user, parse_user_id
from c_application.use_cases.work_calendar._common import own_day_output
from c_application.utils.date_input import DateInput, local_today, resolve_horizon
from c_application.utils.work_calendar import load_work_calendar

DEFAULT_AHEAD_DAYS: int = 365
"""How far the calendar looks ahead when not asked: a year."""

MAX_AHEAD_DAYS: int = 3660
"""The furthest it looks: ten years."""


@dataclass(frozen=True, kw_only=True)
class ShowWorkCalendarInputDTO(DTO):
    """Request to see the user's business days.

    Attributes:
        user_id (str): The user.
        ahead (int | DateInput | None): How far to look: a number of days or
            a date (default: a year).
    """

    user_id: str
    ahead: int | DateInput | None = None


class ShowWorkCalendarUseCase(UseCase[ShowWorkCalendarInputDTO, WorkCalendarOutputDTO]):
    """The user's work days, holiday region, and the special days ahead."""

    async def execute(self, request: ShowWorkCalendarInputDTO) -> WorkCalendarOutputDTO:
        """Show the calendar from today to the horizon.

        Raises:
            ValidationException: If the user ID is invalid.
            EntityNotFound: If the user does not exist.
            InvalidValueError: If ``ahead`` is not a number of days or a date,
                or is more than ten years ahead.
        """
        user_id = parse_user_id(request.user_id)
        async with self.uow as uow:
            user: User = await load_user(uow, user_id)
            prefs = user.preferences
            calendar: WorkCalendar = await load_work_calendar(uow, user_id, prefs)
            suggested: str | None = (
                None
                if prefs.holiday_region
                else uow.holidays.region_for_timezone(prefs.timezone)
            )

        today: date = local_today(self.clock.now(), prefs.timezone)
        until: date = resolve_horizon(
            request.ahead if request.ahead is not None else DEFAULT_AHEAD_DAYS,
            today=today,
        )
        if (until - today).days > MAX_AHEAD_DAYS:
            raise InvalidValueError(
                concept="days ahead (up to ten years)",
                invalid_value=str(request.ahead),
            )

        days: list[CalendarDayOutputDTO] = []
        current: date = today
        while current <= until:
            entry: CalendarDayOutputDTO | None = _entry(current, calendar)
            if entry is not None:
                days.append(entry)
            current += timedelta(days=1)

        return WorkCalendarOutputDTO(
            work_days=prefs.work_days,
            holiday_region=prefs.holiday_region,
            suggested_region=suggested,
            start=today.isoformat(),
            until=until.isoformat(),
            days=days,
            skipped_holidays=[
                n.strip() for n in prefs.skipped_holidays.split(";") if n.strip()
            ],
        )


def _entry(day: date, calendar: WorkCalendar) -> CalendarDayOutputDTO | None:
    """What makes ``day`` special, if anything."""
    own: CalendarDay | None = calendar.own_day(day)
    if own is not None:
        return own_day_output(own, day, calendar)
    holiday: str | None = calendar.holiday(day)
    if holiday is None:
        return None
    return CalendarDayOutputDTO(
        date=day.isoformat(),
        name=holiday,
        source="holiday",
        is_business_day=calendar.is_business_day(day),
        skipped=calendar.is_skipped(day),
    )
