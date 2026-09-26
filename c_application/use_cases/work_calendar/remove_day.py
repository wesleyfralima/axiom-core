from dataclasses import dataclass
from datetime import date, datetime

from a_core import DTO, EntityNotFound
from b_domain.entities import User
from b_domain.ports.use_case import UseCase
from b_domain.value_objects.work_calendar import CalendarDay, WorkCalendar
from c_application.dtos.calendar_dtos import CalendarDayChangedOutputDTO
from c_application.use_cases.context._common import load_user, parse_user_id
from c_application.use_cases.work_calendar._common import next_date, own_day_output
from c_application.utils.date_input import DateInput, local_today, resolve_date_input
from c_application.utils.work_calendar import load_work_calendar


@dataclass(frozen=True, kw_only=True)
class RemoveCalendarDayInputDTO(DTO):
    """Request to remove one of the user's days.

    Attributes:
        user_id (str): The user.
        date (DateInput): A date the day falls on (for a yearly day, any
            year's: ``12-24`` is enough).
        yearly (bool | None): Which one, when a date has both: True for the
            yearly day, False for the one-off. None: the one-off if there is
            one, else the yearly day.
    """

    user_id: str
    date: DateInput
    yearly: bool | None = None


class RemoveCalendarDayUseCase(
    UseCase[RemoveCalendarDayInputDTO, CalendarDayChangedOutputDTO]
):
    """Remove one of the user's days: the date goes back to what it was."""

    async def execute(
        self, request: RemoveCalendarDayInputDTO
    ) -> CalendarDayChangedOutputDTO:
        """Remove the day.

        Raises:
            ValidationException: If the user ID is invalid.
            EntityNotFound: If the user does not exist, or has no such day.
            InvalidValueError: If the date is not valid.
        """
        user_id = parse_user_id(request.user_id)
        async with self.uow as uow:
            user: User = await load_user(uow, user_id)
            today: date = local_today(self.clock.now(), user.preferences.timezone)
            typed: date | datetime = resolve_date_input(request.date, today=today)
            on: date = typed.date() if isinstance(typed, datetime) else typed

            calendar: WorkCalendar = await load_work_calendar(
                uow, user_id, user.preferences
            )
            one_off: CalendarDay | None = next(
                (d for d in calendar.days if not d.yearly and d.day == on), None
            )
            yearly: CalendarDay | None = next(
                (
                    d
                    for d in calendar.days
                    if d.yearly and (d.day.month, d.day.day) == (on.month, on.day)
                ),
                None,
            )
            found: CalendarDay | None = (
                one_off
                if request.yearly is False
                else yearly
                if request.yearly is True
                else one_off or yearly
            )
            if found is None:
                raise EntityNotFound(entity_name="Day of yours", identifier=str(on))
            await uow.calendar_days.remove(user_id, found.day, found.yearly)

        return CalendarDayChangedOutputDTO(
            action="removed",
            day=own_day_output(found, next_date(found, today), calendar),
        )
