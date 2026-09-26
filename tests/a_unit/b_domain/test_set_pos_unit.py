"""set_pos: the Nth day of the week or of the month — never silently ignored."""

from datetime import datetime

import pytest

from b_domain.exceptions import (
    BySetPosRequiresWeeklyOrMonthly,
    BySetPosWithMonthDays,
    BySetPosWithWeekdaysInAWeek,
)
from b_domain.value_objects import RecurrenceInterval
from b_domain.value_objects.dates import AxiomDate
from b_domain.value_objects.recurrences import (
    MonthlyPositionalRule,
    MonthlyWeekdayPositionalRule,
    RecurrenceFactory,
    RecurrenceRule,
    WeeklyPositionalRule,
)

pytestmark = pytest.mark.unit

START = AxiomDate.floating(datetime(2026, 3, 4, 7, 0), "UTC")  # a Wednesday


def _wall(moment: datetime | None) -> datetime | None:
    """Rules hand floating occurrences back with a zone; compare wall-clock time."""
    return moment.replace(tzinfo=None) if moment else None


def _rule(frequency: RecurrenceInterval, **kwargs: object) -> RecurrenceRule:
    return RecurrenceFactory.create_from_input(
        start_date=START,
        frequency=frequency,
        **kwargs,  # type: ignore[arg-type]
    )


@pytest.mark.parametrize(
    ("set_pos", "week_start", "weekday", "first_day"),
    [
        (2, 0, 1, 10),  # week from Monday: 2nd day = Tuesday → Tue 10
        (-1, 0, 6, 8),  # last day = Sunday → Sun 8
        (1, 6, 6, 8),  # week from Sunday: 1st day = Sunday
        (-1, 6, 5, 7),  # week from Sunday: last day = Saturday → Sat 7
        (3, 0, 2, 4),  # 3rd day = Wednesday: the start itself
    ],
)
def test_the_nth_day_of_the_week(
    set_pos: int, week_start: int, weekday: int, first_day: int
) -> None:
    rule = _rule(RecurrenceInterval.WEEKLY, set_pos=set_pos, week_start=week_start)

    assert isinstance(rule, WeeklyPositionalRule)
    assert rule.weekday == weekday
    first = rule.get_next_occurrence()
    assert _wall(first) == datetime(2026, 3, first_day, 7, 0)
    assert _wall(rule.get_next_occurrence(first)) == datetime(
        2026, 3, first_day + 7, 7, 0
    )


def test_the_weekly_position_describes_itself() -> None:
    rule = _rule(RecurrenceInterval.WEEKLY, set_pos=-1)

    assert rule.describe_pattern() == "Every week on the last day (Sunday)"
    assert "BYSETPOS=-1" in rule.rrule_string
    assert "WKST=MO" in rule.rrule_string


@pytest.mark.parametrize("set_pos", [0, 8, -8])
def test_the_weekly_position_has_bounds(set_pos: int) -> None:
    with pytest.raises(Exception, match="1 to 7 or -1 to -7"):
        _rule(RecurrenceInterval.WEEKLY, set_pos=set_pos)


def test_the_monthly_positions_stay() -> None:
    last_day = _rule(RecurrenceInterval.MONTHLY, set_pos=-1)
    second_friday = _rule(RecurrenceInterval.MONTHLY, set_pos=2, days_of_week={4})

    assert isinstance(last_day, MonthlyPositionalRule)
    assert _wall(last_day.get_next_occurrence()) == datetime(2026, 3, 31, 7, 0)
    assert isinstance(second_friday, MonthlyWeekdayPositionalRule)
    assert _wall(second_friday.get_next_occurrence()) == datetime(2026, 3, 13, 7, 0)


@pytest.mark.parametrize(
    ("frequency", "kwargs", "error"),
    [
        (RecurrenceInterval.DAILY, {}, BySetPosRequiresWeeklyOrMonthly),
        (RecurrenceInterval.YEARLY, {}, BySetPosRequiresWeeklyOrMonthly),
        (RecurrenceInterval.HOURLY, {}, BySetPosRequiresWeeklyOrMonthly),
        (
            RecurrenceInterval.MONTHLY,
            {"days_of_month": {1, 15}},
            BySetPosWithMonthDays,
        ),
        (
            RecurrenceInterval.WEEKLY,
            {"days_of_week": {0, 2}},
            BySetPosWithWeekdaysInAWeek,
        ),
    ],
)
def test_a_position_is_never_silently_dropped(
    frequency: RecurrenceInterval, kwargs: dict[str, object], error: type
) -> None:
    with pytest.raises(error):
        _rule(frequency, set_pos=2, **kwargs)
