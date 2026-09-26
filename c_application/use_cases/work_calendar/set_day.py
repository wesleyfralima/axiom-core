from dataclasses import dataclass
from datetime import date, datetime

from a_core import DTO
from a_core.exceptions import InvalidValueError
from b_domain.entities import User
from b_domain.ports.use_case import UseCase
from b_domain.value_objects.work_calendar import (
    CalendarDay,
    CalendarDayKind,
    WorkCalendar,
)
from c_application.dtos.calendar_dtos import CalendarDayChangedOutputDTO
from c_application.use_cases.context._common import load_user, parse_user_id
from c_application.use_cases.work_calendar._common import next_date, own_day_output
from c_application.utils.date_input import DateInput, local_today, resolve_date_input
from c_application.utils.work_calendar import load_work_calendar


@dataclass(frozen=True, kw_only=True)
class SetCalendarDayInputDTO(DTO):
    """Request to make a date a day off or a working day.

    Attributes:
        user_id (str): The user.
        date (DateInput): The date (``2026-12-24``, ``12-24`` for the next
            one, ``tomorrow``…).
        kind (str): ``day_off`` or ``workday``.
        yearly (bool): Every year on that month and day (from that year on),
            instead of only that date.
        name (str | None): What the day is ("Company recess").
    """

    user_id: str
    date: DateInput
    kind: str
    yearly: bool = False
    name: str | None = None


class SetCalendarDayUseCase(
    UseCase[SetCalendarDayInputDTO, CalendarDayChangedOutputDTO]
):
    """Add one of the user's days, or change the one on that date.

    A day off makes a date not a business day, whatever it is; a working day
    makes it one, even on a holiday or a weekend. A date has at most one
    one-off day and one yearly day; setting it again replaces it.
    """

    async def execute(
        self, request: SetCalendarDayInputDTO
    ) -> CalendarDayChangedOutputDTO:
        """Set the day.

        Raises:
            ValidationException: If the user ID or the name is invalid.
            EntityNotFound: If the user does not exist.
            InvalidValueError: If the date or the kind is not valid.
        """
        user_id = parse_user_id(request.user_id)
        try:
            kind: CalendarDayKind = CalendarDayKind(request.kind)
        except ValueError:
            raise InvalidValueError(
                concept="kind of day",
                invalid_value=request.kind,
                valid_options=[k.value for k in CalendarDayKind],
            ) from None

        async with self.uow as uow:
            user: User = await load_user(uow, user_id)
            today: date = local_today(self.clock.now(), user.preferences.timezone)
            typed: date | datetime = resolve_date_input(request.date, today=today)
            day: CalendarDay = CalendarDay(
                day=typed.date() if isinstance(typed, datetime) else typed,
                kind=kind,
                yearly=request.yearly,
                name=request.name or "",
            )

            before: WorkCalendar = await load_work_calendar(
                uow, user_id, user.preferences
            )
            existing: CalendarDay | None = next(
                (d for d in before.days if d.day == day.day and d.yearly == day.yearly),
                None,
            )
            await uow.calendar_days.save(user_id, day)

        on: date = next_date(day, today)
        after: WorkCalendar = WorkCalendar(
            work_days=before.work_days,
            region=before.region,
            holidays=before.holidays,
            days=(*(d for d in before.days if d != existing), day),
        )
        return CalendarDayChangedOutputDTO(
            action="added" if existing is None else "replaced",
            day=own_day_output(day, on, after),
            changes_nothing=before.is_business_day(on) == after.is_business_day(on),
        )
