"""A ``RecurrenceInputDTO`` made into a rule — the same way on create and edit."""

from collections.abc import Callable
from datetime import date, datetime, time

from b_domain.value_objects.dates import build_axiom_date
from b_domain.value_objects.recurrences import RecurrenceFactory, RecurrenceRule
from b_domain.value_objects.work_calendar import weekdays_only
from c_application.dtos.recurrence_dtos import RecurrenceInputDTO
from c_application.utils.date_input import at_time, resolve_date_input

WEEK_STARTS: dict[str, int] = {"monday": 0, "sunday": 6}
"""The ``week_start`` preference as a weekday number."""


def build_recurrence(
    dto: RecurrenceInputDTO,
    *,
    start: datetime,
    is_floating: bool,
    tz: str,
    today: date,
    week_start: int = 0,
    is_business_day: Callable[[date], bool] = weekdays_only,
) -> RecurrenceRule:
    """The rule for ``dto``, starting at ``start``.

    Args:
        dto (RecurrenceInputDTO): What the user asked for.
        start (datetime): The first date, already resolved (its time of day
            is the time of every occurrence).
        is_floating (bool): The due date's kind; the rule takes the same.
        tz (str): The time zone the dates are in.
        today (date): The user's today, for an end date typed as a word.
        week_start (int): The user's first day of the week (0 = Monday,
            6 = Sunday), for "the Nth day of the week".
        is_business_day (Callable[[date], bool]): The user's business days,
            for "the Nth business day" (``WorkCalendar.is_business_day``).

    Returns:
        RecurrenceRule: The rule.

    Raises:
        DomainException: If the combination is invalid (the factory's and the
            rules' own checks).
    """

    end_axiom = None
    if dto.end_date is not None:
        # A date alone: the whole of that day
        end_axiom = build_axiom_date(
            at_time(resolve_date_input(dto.end_date, today=today), time(23, 59)),
            is_floating=is_floating,
            tz=tz,
        )

    return RecurrenceFactory.create_from_input(
        start_date=build_axiom_date(start, is_floating=is_floating, tz=tz),
        end_date=end_axiom,
        frequency=dto.frequency,
        interval=dto.interval,
        count=dto.count,
        days_of_week=set(dto.by_week_days) if dto.by_week_days else None,
        days_of_month=set(dto.by_month_days) if dto.by_month_days else None,
        set_pos=dto.by_set_pos,
        nth_business_day=dto.nth_business_day,
        is_business_day_checker=is_business_day,
        window_start=dto.window_start,
        window_end=dto.window_end,
        week_start=week_start,
        keep_missed=dto.keep_missed,
    )
