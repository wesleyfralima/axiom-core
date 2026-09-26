"""A ``RecurrenceInputDTO`` made into a rule — the same way on create and edit."""

from datetime import date, datetime, time

from b_domain.value_objects.dates import build_axiom_date
from b_domain.value_objects.recurrences import RecurrenceFactory, RecurrenceRule
from c_application.dtos.recurrence_dtos import RecurrenceInputDTO
from c_application.utils.date_input import at_time, resolve_date_input


def build_recurrence(
    dto: RecurrenceInputDTO,
    *,
    start: datetime,
    is_floating: bool,
    tz: str,
    today: date,
) -> RecurrenceRule:
    """The rule for ``dto``, starting at ``start``.

    Args:
        dto (RecurrenceInputDTO): What the user asked for.
        start (datetime): The first date, already resolved (its time of day
            is the time of every occurrence).
        is_floating (bool): The due date's kind; the rule takes the same.
        tz (str): The time zone the dates are in.
        today (date): The user's today, for an end date typed as a word.

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
        is_business_day_checker=lambda dt: dt.weekday() < 5,  # TODO: holidays
        window_start=dto.window_start,
        window_end=dto.window_end,
    )
