"""Every rule survives being turned into data and back (undo snapshots)."""

import json
from datetime import datetime, time

import pytest

from b_domain.value_objects import RecurrenceInterval, recurrences
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
    WeeklyPositionalRule,
)
from b_domain.value_objects.recurrences._serial import rule_from_dict, rule_to_dict

pytestmark = pytest.mark.unit

START = AxiomDate.floating(datetime(2026, 1, 5, 9, 0), "America/Sao_Paulo")
END = AxiomDate.floating(datetime(2026, 12, 31, 9, 0), "America/Sao_Paulo")
FIXED = AxiomDate.fixed(datetime.fromisoformat("2026-01-05T12:00:00+00:00"))

RULES: list[RecurrenceRule] = [
    SimpleIntervalRule(start_date=START, frequency=RecurrenceInterval.DAILY, count=5),
    SimpleIntervalRule(start_date=FIXED, frequency=RecurrenceInterval.WEEKLY),
    WeeklyByDaysRule(start_date=START, days_of_week={0, 2, 4}, end_date=END),
    WeeklyPositionalRule(start_date=START, set_pos=-1, week_start=6),
    MonthlyByDaysRule(start_date=START, days_of_month={5, 20}),
    MonthlyPositionalRule(start_date=START, set_pos=-1),
    MonthlyWeekdayPositionalRule(start_date=START, days_of_week={4}, set_pos=2),
    MonthlyAllWeekdaysRule(start_date=START, days_of_week={1, 3}, interval=2),
    BusinessDayRule(
        start_date=START, nth_day=5, is_business_day=lambda d: d.weekday() < 5
    ),
    HourlyWindowRule(start_date=START, window_start=time(8), window_end=time(20)),
]


def test_every_rule_class_is_covered() -> None:
    names = {
        n
        for n in recurrences.__all__
        if n not in {"RecurrenceRule", "RecurrenceFactory"}
    }
    assert {type(r).__name__ for r in RULES} == names


@pytest.mark.parametrize("rule", RULES, ids=lambda r: type(r).__name__)
def test_a_rule_comes_back_the_same(rule: RecurrenceRule) -> None:
    back = rule_from_dict(json.loads(json.dumps(rule_to_dict(rule))))

    assert back == rule
    assert back.describe_pattern() == rule.describe_pattern()
    assert back.get_next_n_occurrences(4) == rule.get_next_n_occurrences(4)


def test_an_unknown_rule_is_refused() -> None:
    with pytest.raises(ValueError, match="Unknown recurrence rule"):
        rule_from_dict({"type": "LunarRule"})
