from datetime import date, datetime, time

import pytest

from b_domain.value_objects import RecurrenceInterval
from b_domain.value_objects.dates import AxiomDate
from b_domain.value_objects.recurrences import (
    BusinessDayRule,
    HourlyWindowRule,
    MonthlyAllWeekdaysRule,
    MonthlyByDaysRule,
    MonthlyPositionalRule,
    MonthlyWeekdayPositionalRule,
    RecurrenceRule,
    SimpleIntervalRule,
    WeeklyByDaysRule,
)
from c_application.utils import format_task_recurrence

pytestmark = pytest.mark.unit

TZ = "America/Sao_Paulo"
START = AxiomDate.floating(datetime(2026, 1, 5, 9, 0), TZ)


def _weekday_only(d: date) -> bool:
    return d.weekday() < 5


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        (
            SimpleIntervalRule(start_date=START, frequency=RecurrenceInterval.DAILY),
            "Every day",
        ),
        (
            SimpleIntervalRule(
                start_date=START, frequency=RecurrenceInterval.WEEKLY, interval=2
            ),
            "Every 2 weeks",
        ),
        (
            SimpleIntervalRule(start_date=START, frequency=RecurrenceInterval.YEARLY),
            "Every year",
        ),
        (
            WeeklyByDaysRule(start_date=START, days_of_week={4, 0, 2}),
            "Every week on Mondays, Wednesdays, and Fridays",
        ),
        (
            MonthlyByDaysRule(start_date=START, days_of_month={20, 10}, interval=3),
            "Every 3 months on days 10 and 20",
        ),
        (
            MonthlyByDaysRule(start_date=START, days_of_month={5}),
            "Every month on day 5",
        ),
        (
            MonthlyPositionalRule(start_date=START, set_pos=15),
            "Every month on day 15",
        ),
        (
            MonthlyPositionalRule(start_date=START, set_pos=-1),
            "Every month on the last day",
        ),
        (
            MonthlyPositionalRule(start_date=START, set_pos=-3),
            "Every month on the third to last day",
        ),
        (
            MonthlyWeekdayPositionalRule(start_date=START, days_of_week={4}, set_pos=2),
            "Every month on the second Friday",
        ),
        (
            MonthlyWeekdayPositionalRule(
                start_date=START, days_of_week={0, 2}, set_pos=-1
            ),
            "Every month on the last Monday and Wednesday",
        ),
        (
            MonthlyAllWeekdaysRule(start_date=START, days_of_week={1, 3}, interval=2),
            "Every 2 months on every Tuesday and Thursday",
        ),
        (
            BusinessDayRule(start_date=START, nth_day=5, is_business_day=_weekday_only),
            "Every month on the 5th business day",
        ),
        (
            BusinessDayRule(
                start_date=START, nth_day=-1, is_business_day=_weekday_only
            ),
            "Every month on the last business day",
        ),
        (
            HourlyWindowRule(
                start_date=START,
                window_start=time(8, 0),
                window_end=time(20, 0),
                interval=2,
            ),
            "Every 2 hours between 08:00 and 20:00",
        ),
    ],
)
def test_each_rule_describes_its_pattern(rule: RecurrenceRule, expected: str) -> None:
    assert rule.describe_pattern() == expected


def test_format_adds_count() -> None:
    rule = WeeklyByDaysRule(start_date=START, days_of_week={0}, count=10)

    assert format_task_recurrence(rule) == "Every week on Mondays, for 10 occurrences."


def test_format_adds_single_occurrence() -> None:
    rule = SimpleIntervalRule(
        start_date=START, frequency=RecurrenceInterval.DAILY, count=1
    )

    assert format_task_recurrence(rule) == "Every day, for 1 occurrence."


def test_format_adds_end_date() -> None:
    rule = MonthlyPositionalRule(
        start_date=START,
        set_pos=-1,
        end_date=AxiomDate.floating(datetime(2026, 12, 31, 23, 59), TZ),
    )

    assert (
        format_task_recurrence(rule) == "Every month on the last day, until 2026-12-31."
    )


def test_format_without_rule() -> None:
    assert format_task_recurrence(None) is None


def test_business_day_rules_compare() -> None:
    """Equality compares every field, including the internal frequency."""

    def rule(nth: int) -> BusinessDayRule:
        return BusinessDayRule(
            start_date=START, nth_day=nth, is_business_day=_weekday_only
        )

    assert rule(5) == rule(5)
    assert rule(5) != rule(-1)
