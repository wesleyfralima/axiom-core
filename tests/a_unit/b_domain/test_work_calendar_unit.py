"""What a business day is: work days, a region's holidays, the user's own days."""

from collections.abc import Mapping
from datetime import date, datetime

import pytest

from a_core.exceptions import InvalidValueError, ValidationException
from b_domain.entities import UserPrefs
from b_domain.value_objects.dates import AxiomDate
from b_domain.value_objects.enums import RecurrenceInterval
from b_domain.value_objects.recurrences import BusinessDayRule, SimpleIntervalRule
from b_domain.value_objects.work_calendar import (
    CalendarDay,
    CalendarDayKind,
    WorkCalendar,
    parse_work_days,
    weekdays_only,
    work_days_text,
)

pytestmark = pytest.mark.unit

OFF = CalendarDayKind.DAY_OFF
WORK = CalendarDayKind.WORKDAY

# 2026-04-03 is Good Friday; 2026-04-04 a Saturday
GOOD_FRIDAY = date(2026, 4, 3)
SATURDAY = date(2026, 4, 4)


def _holidays(year: int) -> Mapping[date, str]:
    return {GOOD_FRIDAY: "Good Friday"} if year == 2026 else {}


# ---------------------------------------------------------------- work days


@pytest.mark.parametrize(
    ("text", "days"),
    [
        ("mon,tue,wed,thu,fri", {0, 1, 2, 3, 4}),
        ("Monday Wednesday", {0, 2}),
        ("mon-fri", {0, 1, 2, 3, 4}),
        ("sun-thu", {6, 0, 1, 2, 3}),
        ("mon-sat, sun", set(range(7))),
    ],
)
def test_work_days_as_typed(text: str, days: set[int]) -> None:
    assert parse_work_days(text) == frozenset(days)


@pytest.mark.parametrize("text", ["", "funday", "mon-xyz"])
def test_work_days_refused(text: str) -> None:
    with pytest.raises(InvalidValueError, match="work days"):
        parse_work_days(text)


def test_work_days_text_is_canonical() -> None:
    assert work_days_text({4, 0, 6}) == "mon,fri,sun"


def test_preferences_normalize_the_work_days() -> None:
    prefs = UserPrefs().update(work_days="Sun-Thu")
    assert prefs.work_days == "mon,tue,wed,thu,sun"
    assert prefs.work_weekdays == frozenset({0, 1, 2, 3, 6})
    assert UserPrefs().work_weekdays == frozenset(range(5))


@pytest.mark.parametrize(
    ("typed", "stored"),
    [("br", "BR"), (" br-sp ", "BR-SP"), ("us_ca", "US-CA"), ("none", ""), ("", "")],
)
def test_preferences_normalize_the_region(typed: str, stored: str) -> None:
    assert UserPrefs().update(holiday_region=typed).holiday_region == stored


@pytest.mark.parametrize("typed", ["Brazil", "B", "BR-", "BR-TOOLONG"])
def test_a_region_must_look_like_one(typed: str) -> None:
    with pytest.raises(InvalidValueError, match="holiday region"):
        UserPrefs().update(holiday_region=typed)


# ---------------------------------------------------------------- own days


def test_a_one_off_day_falls_on_its_date_only() -> None:
    day = CalendarDay(day=date(2026, 12, 24), kind=OFF)
    assert day.applies_to(date(2026, 12, 24))
    assert not day.applies_to(date(2027, 12, 24))


def test_a_yearly_day_falls_every_year_from_its_own() -> None:
    day = CalendarDay(day=date(2026, 1, 25), kind=OFF, yearly=True)
    assert day.applies_to(date(2026, 1, 25))
    assert day.applies_to(date(2031, 1, 25))
    assert not day.applies_to(date(2025, 1, 25))
    assert not day.applies_to(date(2026, 1, 26))


def test_a_yearly_29_february_only_on_leap_years() -> None:
    day = CalendarDay(day=date(2028, 2, 29), kind=OFF, yearly=True)
    assert day.applies_to(date(2032, 2, 29))
    assert not day.applies_to(date(2029, 2, 28))


def test_a_day_name_is_trimmed_and_limited() -> None:
    assert CalendarDay(day=SATURDAY, kind=OFF, name="  Recess  ").name == "Recess"
    with pytest.raises(ValidationException):
        CalendarDay(day=SATURDAY, kind=OFF, name="x" * 101)


# ---------------------------------------------------------------- the calendar


def test_by_default_monday_to_friday() -> None:
    calendar = WorkCalendar()
    assert calendar.is_business_day(date(2026, 4, 2))
    assert not calendar.is_business_day(SATURDAY)


def test_the_work_days_decide_the_week() -> None:
    calendar = WorkCalendar(work_days=parse_work_days("sun-thu"))
    assert calendar.is_business_day(date(2026, 4, 5))  # Sunday
    assert not calendar.is_business_day(GOOD_FRIDAY)


def test_a_holiday_is_not_a_business_day() -> None:
    calendar = WorkCalendar(region="BR", holidays=_holidays)
    assert calendar.holiday(GOOD_FRIDAY) == "Good Friday"
    assert not calendar.is_business_day(GOOD_FRIDAY)
    assert calendar.is_business_day(date(2026, 4, 2))


def test_own_days_win_over_holidays_and_weekends() -> None:
    calendar = WorkCalendar(
        holidays=_holidays,
        days=(
            CalendarDay(day=GOOD_FRIDAY, kind=WORK),
            CalendarDay(day=SATURDAY, kind=WORK),
            CalendarDay(day=date(2026, 4, 2), kind=OFF),
        ),
    )
    assert calendar.is_business_day(GOOD_FRIDAY)
    assert calendar.is_business_day(SATURDAY)
    assert not calendar.is_business_day(date(2026, 4, 2))


def test_a_one_off_day_wins_over_a_yearly_one() -> None:
    calendar = WorkCalendar(
        days=(
            CalendarDay(day=date(2020, 4, 2), kind=OFF, yearly=True),
            CalendarDay(day=date(2026, 4, 2), kind=WORK),
        )
    )
    assert calendar.is_business_day(date(2026, 4, 2))
    assert not calendar.is_business_day(date(2027, 4, 2))


def test_holidays_are_asked_once_per_year() -> None:
    asked: list[int] = []

    def lookup(year: int) -> Mapping[date, str]:
        asked.append(year)
        return _holidays(year)

    calendar = WorkCalendar(holidays=lookup)
    for day in range(1, 31):
        calendar.is_business_day(date(2026, 4, day))
    assert asked == [2026]


# ---------------------------------------------------------------- the rule


def _fifth_business_day() -> BusinessDayRule:
    return BusinessDayRule(
        start_date=AxiomDate.floating(datetime(2026, 4, 1, 9), "UTC"), nth_day=5
    )


def _day(rule: BusinessDayRule) -> date | None:
    first: datetime | None = rule.get_next_occurrence()
    return first.date() if first else None


def test_the_rule_counts_monday_to_friday_until_told_otherwise() -> None:
    rule = _fifth_business_day()
    assert rule.is_business_day is weekdays_only
    assert rule.uses_business_days
    assert _day(rule) == date(2026, 4, 7)


def test_the_rule_counts_the_users_business_days() -> None:
    rule = _fifth_business_day()
    calendar = WorkCalendar(holidays=_holidays)

    with_holidays = rule.with_business_days(calendar.is_business_day)

    assert _day(with_holidays) == date(2026, 4, 8)
    # The calendar is not part of the rule
    assert with_holidays == rule


def test_other_rules_ignore_business_days() -> None:
    rule = SimpleIntervalRule(
        start_date=AxiomDate.floating(datetime(2026, 4, 1, 9), "UTC"),
        frequency=RecurrenceInterval.DAILY,
    )
    assert not rule.uses_business_days
    assert rule.with_business_days(lambda _: False) is rule


# ---------------------------------------------------------------- skipped


def test_a_skipped_holiday_is_a_business_day() -> None:
    calendar = WorkCalendar(holidays=_holidays, skipped=frozenset({"good friday"}))

    assert calendar.holiday(GOOD_FRIDAY) == "Good Friday"
    assert calendar.is_skipped(GOOD_FRIDAY)
    assert not calendar.counts_as_holiday(GOOD_FRIDAY)
    assert calendar.is_business_day(GOOD_FRIDAY)


def test_own_days_still_win_over_a_skipped_holiday() -> None:
    calendar = WorkCalendar(
        holidays=_holidays,
        skipped=frozenset({"good friday"}),
        days=(CalendarDay(day=GOOD_FRIDAY, kind=OFF),),
    )
    assert not calendar.is_business_day(GOOD_FRIDAY)


def test_preferences_keep_skipped_holidays_tidy() -> None:
    prefs = UserPrefs().update(
        skipped_holidays=" Corpus  Christi ;corpus christi; Carnival ;"
    )

    assert prefs.skipped_holidays == "Corpus Christi; Carnival"
    assert prefs.skipped_holiday_names == {"corpus christi", "carnival"}
