from datetime import UTC, date, datetime, tzinfo
from zoneinfo import ZoneInfo

import pytest

from a_core import DomainException
from b_domain.exceptions import MutuallyExclusiveEndDateAndCount
from b_domain.value_objects import RecurrenceInterval, RecurrenceRule
from b_domain.value_objects.dates import AxiomDate
from b_domain.value_objects.recurrences import (
    BusinessDayRule,
    MonthlyAllWeekdaysRule,
    MonthlyByDaysRule,
    MonthlyPositionalRule,
    MonthlyWeekdayPositionalRule,
    SimpleIntervalRule,
    WeeklyByDaysRule,
)
from b_domain.value_objects.recurrences.simple import add_months

# Group 1: Validation Rules
# ============================================================


def test_end_date_and_count_are_mutually_exclusive() -> None:
    """Ensure RecurrenceRule does not allow both end_date and count simultaneously."""

    with pytest.raises(MutuallyExclusiveEndDateAndCount):
        SimpleIntervalRule(
            frequency=RecurrenceInterval.DAILY,
            start_date=AxiomDate.floating(datetime(2024, 1, 1), "UTC"),
            end_date=AxiomDate.floating(datetime(2024, 1, 10), "UTC"),
            count=5,
        )


def test_start_date_must_be_before_end_date() -> None:
    """Ensure end_date is strictly after start_date."""

    with pytest.raises(DomainException):
        SimpleIntervalRule(
            frequency=RecurrenceInterval.DAILY,
            start_date=AxiomDate.floating(datetime(2024, 1, 10), "UTC"),
            end_date=AxiomDate.floating(datetime(2024, 1, 9), "UTC"),
        )


@pytest.mark.parametrize(
    "frequency, interval",
    [
        (RecurrenceInterval.DAILY, 1),
        (RecurrenceInterval.DAILY, 366),
        (RecurrenceInterval.WEEKLY, 52),
        (RecurrenceInterval.MONTHLY, 13),
        (RecurrenceInterval.YEARLY, 5),
    ],
)
def test_recurrence_rule_valid_boundaries(
    frequency: RecurrenceInterval,
    interval: int,
) -> None:
    """Ensure recurrence rule accepts boundary values without error."""

    rule = SimpleIntervalRule(
        frequency=frequency,
        start_date=AxiomDate.floating(datetime(2024, 1, 1), "UTC"),
        interval=interval,
    )
    assert rule.interval == interval


def test_week_days_range_validation() -> None:
    """Ensure by_week_days values are between 0 and 6."""

    with pytest.raises(DomainException):
        WeeklyByDaysRule(
            start_date=AxiomDate.floating(datetime(2024, 1, 1), "UTC"),
            days_of_week={7},  # Invalid
        )

    with pytest.raises(DomainException):
        WeeklyByDaysRule(
            start_date=AxiomDate.floating(datetime(2024, 1, 1), "UTC"),
            days_of_week={-1},  # Invalid
        )


def test_month_days_range_validation() -> None:
    """Ensure by_month_days values are between 1 and 31."""

    with pytest.raises(DomainException):
        MonthlyByDaysRule(
            start_date=AxiomDate.floating(datetime(2024, 1, 1), "UTC"),
            days_of_month={32},  # Invalid
        )

    with pytest.raises(DomainException):
        MonthlyByDaysRule(
            start_date=AxiomDate.floating(datetime(2024, 1, 1), "UTC"),
            days_of_month={-1, 0},  # Invalid
        )


def test_nth_business_day_validation() -> None:
    """Ensure nth_business_day requires a predicate and no other conflicting rules."""

    # Falta o predicado is_business_day
    with pytest.raises(DomainException):
        BusinessDayRule(
            start_date=AxiomDate.floating(datetime(2024, 1, 1), "UTC"),
            nth_day=1,
            is_business_day=None,  # type: ignore[arg-type] # noqa
        )


# ============================================================
# Group 2: add_months Utility Function
# ============================================================


def test_add_months_clamps_to_last_day_of_month() -> None:
    """Ensure add_months clamps to the last valid day of the target month."""

    jan_31: datetime = datetime(2024, 1, 31)
    feb: datetime = add_months(jan_31, 1)

    assert feb.year == 2024
    assert feb.month == 2
    assert feb.day == 29  # Leap year


def test_add_months_preserves_target_day_when_possible() -> None:
    """Ensure add_months preserves the target day when valid in the target month."""

    # Preserving 15 as the day
    jan_15: datetime = datetime(2024, 1, 15)
    feb: datetime = add_months(jan_15, 1)
    assert feb.day == 15

    # Preserving 29 as the day (because feb does not have 31 days)
    jan_31: datetime = datetime(2024, 1, 31)
    feb_29: datetime = add_months(jan_31, 1)
    assert feb_29.day == 29

    # the day is preserved, unless target_day is passed
    mar_29: datetime = add_months(feb_29, 1)
    assert mar_29.day == 29

    # target_day should restore the day in the next month;
    # feb_29 has 29 as day, but mar_31 must have 31
    mar_31: datetime = add_months(feb_29, 1, target_day=jan_31.day)
    assert mar_31.day == 31


# ============================================================
# Group 3: Daily Recurrence
# ============================================================


def test_daily_recurrence_every_two_days() -> None:
    """Ensure daily recurrence with interval=2 generates occurrences every two days."""

    start: AxiomDate = AxiomDate.floating(datetime(2024, 1, 1, 10, 0), "UTC")

    rule: RecurrenceRule = SimpleIntervalRule(
        frequency=RecurrenceInterval.DAILY,
        interval=2,
        start_date=start,
    )

    first: datetime | None = rule.get_next_occurrence()
    second: datetime | None = rule.get_next_occurrence(first)

    assert first is not None
    assert first == start.materialize()

    assert second is not None
    assert second == datetime(2024, 1, 3, 10, 0, tzinfo=ZoneInfo(key="UTC"))


def test_recurrence_stops_at_end_date() -> None:
    """Ensure recurrence stops when end_date is reached."""

    rule: RecurrenceRule = SimpleIntervalRule(
        frequency=RecurrenceInterval.DAILY,
        start_date=AxiomDate.floating(datetime(2024, 1, 1), "UTC"),
        end_date=AxiomDate.floating(datetime(2024, 1, 3, 23, 59), "UTC"),
    )

    first: datetime | None = rule.get_next_occurrence()
    second: datetime | None = rule.get_next_occurrence(first)
    third: datetime | None = rule.get_next_occurrence(second)
    fourth: datetime | None = rule.get_next_occurrence(third)

    assert first is not None
    assert first.date() == datetime(2024, 1, 1).date()

    assert second is not None
    assert second.date() == datetime(2024, 1, 2).date()

    assert third is not None
    assert third.date() == datetime(2024, 1, 3).date()
    assert fourth is None


# ============================================================
# Group 4: Weekly Recurrence
# ============================================================


def test_weekly_recurrence_basic() -> None:
    """Ensure weekly recurrence generates occurrences every week by default."""

    start: AxiomDate = AxiomDate.floating(datetime(2024, 1, 1, 10, 0), "UTC")  # Monday

    rule: RecurrenceRule = SimpleIntervalRule(
        frequency=RecurrenceInterval.WEEKLY,
        start_date=start,
    )

    first: datetime | None = rule.get_next_occurrence()
    second: datetime | None = rule.get_next_occurrence(first)

    assert first is not None
    assert first == start.value.replace(tzinfo=ZoneInfo(key="UTC"))

    assert second is not None
    assert second == datetime(2024, 1, 8, 10, 0, tzinfo=ZoneInfo("UTC"))


def test_weekly_recurrence_every_two_weeks() -> None:
    """
    Ensure weekly recurrence with interval=2
    generates occurrences every two weeks.
    """

    start: AxiomDate = AxiomDate.floating(datetime(2024, 1, 1, 10, 0), "UTC")  # Monday

    rule: RecurrenceRule = SimpleIntervalRule(
        frequency=RecurrenceInterval.WEEKLY,
        interval=2,
        start_date=start,
    )

    first: datetime | None = rule.get_next_occurrence()
    second: datetime | None = rule.get_next_occurrence(first)

    assert first is not None
    assert first == start.value.replace(tzinfo=ZoneInfo(key="UTC"))

    assert second is not None
    assert second == datetime(2024, 1, 15, 10, 0, tzinfo=ZoneInfo("UTC"))


def test_weekly_multiple_weekdays() -> None:
    """Ensure weekly recurrence can generate multiple weekdays within the same week."""

    start: AxiomDate = AxiomDate.floating(datetime(2024, 1, 1, 10, 0), "UTC")  # Monday

    rule: RecurrenceRule = WeeklyByDaysRule(
        start_date=start,
        days_of_week={0, 3},  # Monday, Thursday
    )

    first: datetime | None = rule.get_next_occurrence()
    second: datetime | None = rule.get_next_occurrence(first)
    third: datetime | None = rule.get_next_occurrence(second)
    forth: datetime | None = rule.get_next_occurrence(third)

    assert first is not None
    assert first == datetime(2024, 1, 1, 10, 0, tzinfo=ZoneInfo("UTC"))

    assert second is not None
    assert second == datetime(2024, 1, 4, 10, 0, tzinfo=ZoneInfo("UTC"))

    assert third is not None
    assert third == datetime(2024, 1, 8, 10, 0, tzinfo=ZoneInfo("UTC"))

    assert forth is not None
    assert forth == datetime(2024, 1, 11, 10, 0, tzinfo=ZoneInfo("UTC"))


def test_weekly_does_not_return_past_days_before_start_date() -> None:
    """Ensure recurrence does not return past weekdays before the start_date."""

    start: AxiomDate = AxiomDate.floating(
        datetime(2024, 1, 3, 10, 0), "UTC"
    )  # Wednesday

    rule: RecurrenceRule = WeeklyByDaysRule(
        start_date=start,
        days_of_week={0, 2},  # Monday, Wednesday
    )

    # Monday (0) is before start (Wednesday), so should start on Wednesday
    first: datetime | None = rule.get_next_occurrence()

    assert first is not None
    assert first == datetime(2024, 1, 3, 10, 0, tzinfo=ZoneInfo("UTC"))


def test_weekly_interval_with_multiple_weekdays() -> None:
    """Ensure weekly recurrence with interval and multiple weekdays works correctly."""

    start: AxiomDate = AxiomDate.floating(datetime(2024, 1, 1, 10, 0), "UTC")  # Monday

    rule: RecurrenceRule = WeeklyByDaysRule(
        interval=2,
        start_date=start,
        days_of_week={0, 4},  # Monday, Friday
    )

    # First week
    first: datetime | None = rule.get_next_occurrence()
    second: datetime | None = rule.get_next_occurrence(first)
    assert first == datetime(2024, 1, 1, 10, 0, tzinfo=ZoneInfo("UTC"))
    assert second == datetime(2024, 1, 5, 10, 0, tzinfo=ZoneInfo("UTC"))

    # Third week (second week is ignored due to interval=2)
    third: datetime | None = rule.get_next_occurrence(second)
    forth: datetime | None = rule.get_next_occurrence(third)
    assert third == datetime(2024, 1, 15, 10, 0, tzinfo=ZoneInfo("UTC"))
    assert forth == datetime(2024, 1, 19, 10, 0, tzinfo=ZoneInfo("UTC"))


def test_weekly_recurrence_stops_at_end_date() -> None:
    """Ensure weekly recurrence stops when the end_date is reached."""

    rule: RecurrenceRule = WeeklyByDaysRule(
        start_date=AxiomDate.floating(datetime(2024, 1, 1, 10, 0), "UTC"),
        days_of_week={0},  # Monday
        end_date=AxiomDate.floating(datetime(2024, 1, 8, 10, 0), "UTC"),
    )

    first: datetime | None = rule.get_next_occurrence()
    second: datetime | None = rule.get_next_occurrence(first)
    third: datetime | None = rule.get_next_occurrence(second)

    assert first is not None
    assert first.date() == datetime(2024, 1, 1).date()

    assert second is not None
    assert second.date() == datetime(2024, 1, 8).date()

    assert third is None


# ============================================================
# Group 5: Monthly Recurrence
# ============================================================


def test_monthly_recurrence_clamps_end_of_month() -> None:
    """Ensure monthly recurrence clamps to last valid day of month when needed."""

    start: AxiomDate = AxiomDate.floating(datetime(2024, 1, 31, 10, 0), "UTC")

    rule: RecurrenceRule = SimpleIntervalRule(
        frequency=RecurrenceInterval.MONTHLY,
        start_date=start,
    )

    feb: datetime | None = rule.get_next_occurrence(start.value)
    mar: datetime | None = rule.get_next_occurrence(feb)
    abr: datetime | None = rule.get_next_occurrence(mar)

    assert feb == datetime(2024, 2, 29, 10, 0, tzinfo=ZoneInfo("UTC"))
    assert mar == datetime(2024, 3, 31, 10, 0, tzinfo=ZoneInfo("UTC"))
    assert abr == datetime(2024, 4, 30, 10, 0, tzinfo=ZoneInfo("UTC"))


def test_monthly_by_month_days() -> None:
    """Ensure recurrence works with specific days of the month (e.g. 10th and 20th)."""

    # Start date is Jan 1st
    rule = MonthlyByDaysRule(
        start_date=AxiomDate.floating(datetime(2024, 1, 1, 10, 0), "UTC"),
        days_of_month={10, 20},
    )

    # First occurrence should be Jan 10th (since Jan 1st is not in the list)
    first: datetime | None = rule.get_next_occurrence()
    assert first == datetime(2024, 1, 10, 10, 0, tzinfo=ZoneInfo("UTC"))

    second: datetime | None = rule.get_next_occurrence(first)
    assert second == datetime(2024, 1, 20, 10, 0, tzinfo=ZoneInfo("UTC"))

    third: datetime | None = rule.get_next_occurrence(second)
    assert third == datetime(2024, 2, 10, 10, 0, tzinfo=ZoneInfo("UTC"))


def test_monthly_by_weekdays_all_occurrences() -> None:
    """Ensure recurrence returns ALL occurrences of a weekday in the month."""

    # Every Monday (0) in Jan 2024: 1, 8, 15, 22, 29
    rule: RecurrenceRule = MonthlyAllWeekdaysRule(
        start_date=AxiomDate.floating(datetime(2024, 1, 1, 10, 0), "UTC"),
        days_of_week={0},
    )

    occurrences: list[datetime] = []
    current: datetime | None = None
    for _ in range(5):
        current = rule.get_next_occurrence(current)
        assert current is not None
        occurrences.append(current)

    expected: list[datetime] = [
        datetime(2024, 1, 1, 10, 0, tzinfo=ZoneInfo("UTC")),
        datetime(2024, 1, 8, 10, 0, tzinfo=ZoneInfo("UTC")),
        datetime(2024, 1, 15, 10, 0, tzinfo=ZoneInfo("UTC")),
        datetime(2024, 1, 22, 10, 0, tzinfo=ZoneInfo("UTC")),
        datetime(2024, 1, 29, 10, 0, tzinfo=ZoneInfo("UTC")),
    ]
    assert occurrences == expected


def test_monthly_by_set_pos_only_last_day() -> None:
    """Ensure recurrence on last day of month via set_pos=-1."""

    rule: RecurrenceRule = MonthlyPositionalRule(
        start_date=AxiomDate.floating(datetime(2024, 1, 1, 10, 0), "UTC"), set_pos=-1
    )

    jan: datetime | None = rule.get_next_occurrence()
    assert jan == datetime(2024, 1, 31, 10, 0, tzinfo=ZoneInfo("UTC"))

    feb: datetime | None = rule.get_next_occurrence(jan)
    assert feb == datetime(2024, 2, 29, 10, 0, tzinfo=ZoneInfo("UTC"))  # Leap year


def test_first_monday_of_month() -> None:
    """Ensure recurrence can select the first Monday of each month."""

    start: AxiomDate = AxiomDate.floating(datetime(2024, 1, 1, 10, 0), "UTC")  # Monday

    rule: RecurrenceRule = MonthlyWeekdayPositionalRule(
        start_date=start,
        days_of_week={0},
        set_pos=1,
    )

    # First one is Start Date
    first: datetime | None = rule.get_next_occurrence()
    assert first == datetime(2024, 1, 1, 10, 0, tzinfo=ZoneInfo("UTC"))

    feb: datetime | None = rule.get_next_occurrence(first)

    assert feb is not None
    assert feb.date() == datetime(2024, 2, 5).date()


def test_last_friday_of_month() -> None:
    """Ensure recurrence can select the last Friday of each month."""

    rule: RecurrenceRule = MonthlyWeekdayPositionalRule(
        start_date=AxiomDate.floating(datetime(2024, 1, 1, 10, 0), "UTC"),
        days_of_week={4},  # Friday
        set_pos=-1,
    )

    jan: datetime | None = rule.get_next_occurrence()
    assert jan is not None
    assert jan.date() == datetime(2024, 1, 26).date()

    feb: datetime | None = rule.get_next_occurrence(jan)
    assert feb is not None
    assert feb.date() == datetime(2024, 2, 23).date()


def test_fifth_monday_skips_months_without_five_occurrences() -> None:
    """Ensure recurrence skips months without a fifth Monday."""

    rule: RecurrenceRule = MonthlyWeekdayPositionalRule(
        start_date=AxiomDate.floating(datetime(2024, 1, 1, 10, 0), "UTC"),
        days_of_week={0},
        set_pos=5,
    )

    jan: datetime | None = rule.get_next_occurrence()
    apr: datetime | None = rule.get_next_occurrence(jan)

    assert jan is not None
    assert jan.date() == datetime(2024, 1, 29).date()

    # Feb and Mar 2024 don't have 5 Mondays

    assert apr is not None
    assert apr.date() == datetime(2024, 4, 29).date()


# ============================================================
# Group 6: Yearly Recurrence
# ============================================================


def test_yearly_recurrence_from_feb_29() -> None:
    """
    Ensure yearly recurrence handles leap day
     correctly across leap and non-leap years.
    """

    start: AxiomDate = AxiomDate.floating(datetime(2024, 2, 29, 10, 0), "UTC")

    rule: RecurrenceRule = SimpleIntervalRule(
        frequency=RecurrenceInterval.YEARLY,
        start_date=start,
    )

    y2025: datetime | None = rule.get_next_occurrence(start.value)
    y2026: datetime | None = rule.get_next_occurrence(y2025)
    y2028: datetime | None = rule.get_next_occurrence(rule.get_next_occurrence(y2026))

    assert y2025 is not None
    assert y2025.date() == datetime(2025, 2, 28).date()

    assert y2026 is not None
    assert y2026.date() == datetime(2026, 2, 28).date()

    assert y2028 is not None
    assert y2028.date() == datetime(2028, 2, 29).date()


# ============================================================
# Group 7: Business Days
# ============================================================


def simple_business_day(d: date) -> bool:
    # segunda (0) a sexta (4) e não é o ano novo de 2024
    return d.weekday() < 5 and d != date(2024, 1, 1)


def test_fifth_business_day_of_month() -> None:
    """Ensure recurrence selects the 5th business day of the month."""

    start: AxiomDate = AxiomDate.floating(
        datetime(2024, 1, 1, 10, 0), "UTC"
    )  # Jan 1, 2024 is Monday

    rule: RecurrenceRule = BusinessDayRule(
        start_date=start, nth_day=5, is_business_day=simple_business_day
    )

    # 1st business day: Jan 2 (Jan 1 is holiday)
    # 2: Jan 3, 3: Jan 4, 4: Jan 5 (Fri), 5: Jan 8 (Mon)
    jan: datetime | None = rule.get_next_occurrence()
    assert jan is not None
    assert jan.date() == datetime(2024, 1, 8).date()


def test_last_business_day_of_month() -> None:
    """Ensure recurrence selects the last business day of the month."""

    rule: RecurrenceRule = BusinessDayRule(
        start_date=AxiomDate.floating(datetime(2024, 2, 1, 10, 0), "UTC"),
        nth_day=-1,
        is_business_day=simple_business_day,
    )

    feb: datetime | None = rule.get_next_occurrence()
    assert feb is not None
    assert feb.date() == datetime(2024, 2, 29).date()  # Leap year, Friday


def test_business_day_respects_monthly_interval() -> None:
    """Ensure business day recurrence respects interval between months."""

    rule: RecurrenceRule = BusinessDayRule(
        interval=2,
        start_date=AxiomDate.floating(datetime(2024, 1, 1, 10, 0), "UTC"),
        nth_day=1,
        is_business_day=simple_business_day,
    )

    jan: datetime | None = rule.get_next_occurrence()
    assert jan is not None
    assert jan.date() == datetime(2024, 1, 2).date()  # Jan 2 (Jan 1 holiday)

    mar: datetime | None = rule.get_next_occurrence(jan)
    assert mar is not None
    assert mar.date() == datetime(2024, 3, 1).date()  # Mar 1 (Friday)


def test_nth_business_day_out_of_range_returns_none() -> None:
    """Ensure recurrence returns None if nth business day does not exist."""

    rule: RecurrenceRule = BusinessDayRule(
        start_date=AxiomDate.floating(datetime(2024, 2, 1, 10, 0), "UTC"),
        nth_day=30,  # impossible
        is_business_day=simple_business_day,
    )

    result: datetime | None = rule.get_next_occurrence()
    assert result is None


def test_business_day_respects_end_date() -> None:
    """Ensure business day recurrence stops at end_date."""

    rule: RecurrenceRule = BusinessDayRule(
        start_date=AxiomDate.floating(datetime(2024, 1, 1, 10, 0), "UTC"),
        nth_day=5,
        end_date=AxiomDate.floating(datetime(2024, 1, 4, 23, 59), "UTC"),
        is_business_day=simple_business_day,
    )

    result: datetime | None = rule.get_next_occurrence()
    assert result is None


def test_business_day_never_returns_before_start_date() -> None:
    """Ensure business day recurrence does not return dates before start_date."""

    start_date: AxiomDate = AxiomDate.floating(datetime(2024, 1, 10, 10, 0), "UTC")

    rule: RecurrenceRule = BusinessDayRule(
        start_date=start_date, nth_day=1, is_business_day=simple_business_day
    )

    first: datetime | None = rule.get_next_occurrence()
    # 1st business day of Jan is Jan 2, but start_date is Jan 10.
    # Should skip Jan entirely and go to Feb
    assert first is not None
    assert first.date() > start_date.materialize().date()
    assert first.date() == datetime(2024, 2, 1).date()


# ============================================================
# Group 8: _get_closest_occurrence
# ============================================================


def test_get_closest_occurrence_after_reference() -> None:
    """Ensure the closest occurrence after reference is returned."""

    rule = SimpleIntervalRule(
        frequency=RecurrenceInterval.DAILY,
        start_date=AxiomDate.floating(datetime(2024, 1, 1), "UTC"),
        interval=1,
        end_date=AxiomDate.floating(datetime(2024, 1, 10), "UTC"),
    )

    # Reference no dia 3 → deve retornar dia 3 (≥ reference)
    result = rule._get_closest_occurrence(datetime(2024, 1, 3), before=False)
    assert result == datetime(2024, 1, 3, tzinfo=ZoneInfo("UTC"))


def test_get_closest_occurrence_before_reference() -> None:
    """Ensure the closest occurrence before reference is returned."""

    rule = SimpleIntervalRule(
        frequency=RecurrenceInterval.DAILY,
        start_date=AxiomDate.floating(datetime(2024, 1, 1), "UTC"),
        interval=1,
        end_date=AxiomDate.floating(datetime(2024, 1, 10), "UTC"),
    )

    # Reference no dia 5 → deve retornar dia 4 (< reference)
    result = rule._get_closest_occurrence(datetime(2024, 1, 5), before=True)
    assert result == datetime(2024, 1, 4, tzinfo=ZoneInfo("UTC"))


def test_get_closest_occurrence_respects_end_date() -> None:
    """Ensure occurrences beyond end_date are not returned."""

    rule = SimpleIntervalRule(
        frequency=RecurrenceInterval.DAILY,
        start_date=AxiomDate.floating(datetime(2024, 1, 1), "UTC"),
        interval=1,
        end_date=AxiomDate.floating(datetime(2024, 1, 5), "UTC"),
    )

    # Reference no dia 6 → não deve retornar nada, pois end_date é 5
    result = rule._get_closest_occurrence(datetime(2024, 1, 6), before=False)
    assert result is None

    # Reference no dia 15, before=True → deve retornar último válido (dia 5)
    result_before = rule._get_closest_occurrence(datetime(2024, 1, 15), before=True)
    assert result_before == datetime(2024, 1, 5, tzinfo=ZoneInfo("UTC"))


def test_daily_interval_two_days() -> None:
    """Every 2 days recurrence should skip correctly."""

    rule = SimpleIntervalRule(
        frequency=RecurrenceInterval.DAILY,
        start_date=AxiomDate.floating(datetime(2024, 1, 1), "UTC"),
        interval=2,
        end_date=AxiomDate.floating(datetime(2024, 1, 10), "UTC"),
    )

    # Reference dia 3 → próxima ocorrência é dia 3 (porque 1,3,5,...)
    result = rule._get_closest_occurrence(datetime(2024, 1, 3), before=False)
    assert result == datetime(2024, 1, 3, tzinfo=ZoneInfo("UTC"))

    # Reference dia 3 → ocorrência anterior é dia 1 (porque 1,3,5,...)
    result = rule._get_closest_occurrence(datetime(2024, 1, 3), before=True)
    assert result == datetime(2024, 1, 1, tzinfo=ZoneInfo("UTC"))

    # Reference dia 4 → próxima ocorrência é dia 5 (porque 1,3,5,...)
    result = rule._get_closest_occurrence(datetime(2024, 1, 4), before=False)
    assert result == datetime(2024, 1, 5, tzinfo=ZoneInfo("UTC"))

    # Reference dia 4 → ocorrência anterior é dia 3 (porque 1,3,5,...)
    result = rule._get_closest_occurrence(datetime(2024, 1, 4), before=True)
    assert result == datetime(2024, 1, 3, tzinfo=ZoneInfo("UTC"))


def test_weekly_on_specific_weekday() -> None:
    """Weekly recurrence restricted to Mondays."""

    rule = WeeklyByDaysRule(
        start_date=AxiomDate.floating(datetime(2024, 1, 1), "UTC"),  # Monday
        days_of_week={0},  # Monday
        end_date=AxiomDate.floating(datetime(2024, 1, 31), "UTC"),
    )

    # Reference dia 3 (quarta) → próxima ocorrência é dia 8 (1, 8, 15, 22, 29)
    result = rule._get_closest_occurrence(datetime(2024, 1, 3), before=False)
    assert result == datetime(2024, 1, 8, tzinfo=ZoneInfo("UTC"))

    # Reference dia 3 (quarta) → ocorrência anterior é dia 1 (1, 8, 15, 22, 29)
    result = rule._get_closest_occurrence(datetime(2024, 1, 3), before=True)
    assert result == datetime(2024, 1, 1, tzinfo=ZoneInfo("UTC"))

    # Reference dia 18 → próxima ocorrência é dia 22 (1, 8, 15, 22, 29)
    result = rule._get_closest_occurrence(datetime(2024, 1, 18), before=False)
    assert result == datetime(2024, 1, 22, tzinfo=ZoneInfo("UTC"))

    # Reference dia 18 → ocorrência anterior é dia 15 (1, 8, 15, 22, 29)
    result = rule._get_closest_occurrence(datetime(2024, 1, 18), before=True)
    assert result == datetime(2024, 1, 15, tzinfo=ZoneInfo("UTC"))


def test_monthly_on_specific_day() -> None:
    """Monthly recurrence restricted to day 15."""

    rule = MonthlyByDaysRule(
        start_date=AxiomDate.floating(datetime(2024, 1, 1), "UTC"),
        days_of_month={15},
        end_date=AxiomDate.floating(datetime(2024, 3, 31), "UTC"),
    )

    # Reference dia 10/01 → próxima ocorrência é dia 15 de janeiro
    result = rule._get_closest_occurrence(datetime(2024, 1, 10), before=False)
    assert result == datetime(2024, 1, 15, tzinfo=ZoneInfo("UTC"))

    # Reference dia 10/01 → ocorrência anterior None
    result = rule._get_closest_occurrence(datetime(2024, 1, 10), before=True)
    assert result is None

    # Reference dia 20/01 → próxima ocorrência é 15 de fevereiro
    result2 = rule._get_closest_occurrence(datetime(2024, 1, 20), before=False)
    assert result2 == datetime(2024, 2, 15, tzinfo=ZoneInfo("UTC"))

    # Reference dia 20/01 → ocorrência anterior é 15 de janeiro
    result2 = rule._get_closest_occurrence(datetime(2024, 1, 20), before=True)
    assert result2 == datetime(2024, 1, 15, tzinfo=ZoneInfo("UTC"))


def test_monthly_positional_rule_last_friday() -> None:
    """Monthly recurrence restricted to last Friday of the month."""

    rule = MonthlyWeekdayPositionalRule(
        start_date=AxiomDate.floating(datetime(2024, 1, 1), "UTC"),
        days_of_week={4},  # Friday
        set_pos=-1,  # Last
        end_date=AxiomDate.floating(datetime(2024, 3, 31), "UTC"),
    )

    # Reference dia 10/01 → próxima ocorrência é dia 26/01
    result = rule._get_closest_occurrence(datetime(2024, 1, 10), before=False)
    assert result == datetime(2024, 1, 26, tzinfo=ZoneInfo("UTC"))

    # Reference dia 10/01 → ocorrência anterior é None
    result = rule._get_closest_occurrence(datetime(2024, 1, 10), before=True)
    assert result is None

    # Reference dia 10/03 → próxima ocorrência é dia 29/03
    result = rule._get_closest_occurrence(datetime(2024, 3, 10), before=False)
    assert result == datetime(2024, 3, 29, tzinfo=ZoneInfo("UTC"))

    # Reference dia 10/03 → ocorrência anterior é dia 23/02
    result = rule._get_closest_occurrence(datetime(2024, 3, 10), before=True)
    assert result == datetime(2024, 2, 23, tzinfo=ZoneInfo("UTC"))


def test_monthly_nth_business_day() -> None:
    """Monthly recurrence restricted to nth business day."""

    def is_business_day(d: date) -> bool:
        return d.weekday() < 5  # Mon-Fri

    rule = BusinessDayRule(
        start_date=AxiomDate.floating(datetime(2024, 1, 1), "UTC"),
        nth_day=3,
        is_business_day=is_business_day,
        end_date=AxiomDate.floating(datetime(2024, 3, 31), "UTC"),
    )

    # Reference dia 02/01 → próxima ocorrência é dia 03/01
    result = rule._get_closest_occurrence(datetime(2024, 1, 2), before=False)
    assert result == datetime(2024, 1, 3, tzinfo=ZoneInfo("UTC"))

    # Reference dia 10/01 → ocorrência anterior é 03/01
    result = rule._get_closest_occurrence(datetime(2024, 1, 10), before=True)
    assert result == datetime(2024, 1, 3, tzinfo=ZoneInfo("UTC"))

    # Reference dia 02/03 → próxima ocorrência é dia 05/03
    result = rule._get_closest_occurrence(datetime(2024, 3, 2), before=False)
    assert result == datetime(2024, 3, 5, tzinfo=ZoneInfo("UTC"))

    # Reference dia 10/03 → ocorrência anterior é dia 05/03
    result = rule._get_closest_occurrence(datetime(2024, 3, 10), before=True)
    assert result == datetime(2024, 3, 5, tzinfo=ZoneInfo("UTC"))


# ============================================================
# Group 9: Timezone Consistency & Agnostic Behavior
# ============================================================


def test_constructor_enforces_timezone_consistency_naive_start_aware_end() -> None:
    """
    Ensure we cannot create a rule with Naive start (Floating) and Aware end (Fixed).
    Must raise DomainException (ValidationException).
    """

    with pytest.raises(DomainException) as exc:
        SimpleIntervalRule(
            frequency=RecurrenceInterval.DAILY,
            start_date=AxiomDate.floating(
                datetime(2026, 1, 1), "UTC"
            ),  # Naive (Floating)
            end_date=AxiomDate.fixed(
                datetime(2026, 1, 10, tzinfo=UTC)
            ),  # Aware (Fixed)
        )
        assert "must both be timezone-aware or both be naive" in str(exc.value)


def test_constructor_enforces_timezone_consistency_aware_start_naive_end() -> None:
    """
    Ensure we cannot create a rule with Aware start (Fixed) and Naive end (Floating).
    """

    with pytest.raises(DomainException) as exc:
        SimpleIntervalRule(
            frequency=RecurrenceInterval.DAILY,
            start_date=AxiomDate.fixed(datetime(2026, 1, 1, tzinfo=UTC)),  # Aware
            end_date=AxiomDate.floating(datetime(2026, 1, 10), "UTC"),  # Naive
        )
        assert "must both be timezone-aware or both be naive" in str(exc.value)


def test_floating_rule_sanitizes_aware_input() -> None:
    """
    Scenario: User has a Floating task (Every day at 09:00 Wall Clock).
    Input: The system passes a 'last_occurrence' or 'reference' that is UTC (Aware).
    Expected: The rule should strip the tz from the input and treat it as 09:00 naive.
    """

    # 1. Regra Floating (Naive) - Todo dia às 09:00
    rule = SimpleIntervalRule(
        frequency=RecurrenceInterval.DAILY,
        start_date=AxiomDate.floating(
            datetime(2026, 1, 1, 9, 0, 0), "America/Sao_Paulo"
        ),
        interval=1,
    )

    # 2. Input "sujo" com UTC (Ex: 09:00 UTC)
    # Se o sistema não sanitizasse, isso daria TypeError aqui.
    input_aware = datetime(2026, 1, 1, 9, 0, 0, tzinfo=UTC)

    # 3. Executa
    next_occurrence = rule.get_next_occurrence(last_occurrence=input_aware)

    # 4. Verifica
    # Deve retornar 02/01 às 09:00 NAIVE (Floating)
    expected = datetime(2026, 1, 2, 9, 0, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))

    assert next_occurrence is not None
    assert next_occurrence.tzinfo is ZoneInfo("America/Sao_Paulo")
    assert next_occurrence == expected


def test_floating_rule_ignores_timezone_offset_semantics() -> None:
    """
    Scenario: Floating Rule at 10:00.
    Input: A date representing 10:00-03:00 (Sao Paulo).

    Critical: The rule is 'Timezone Agnostic' (Wall Clock).
    It should see "10:00" in the input and ignore the "-03:00".
    It should NOT convert to UTC first. 10:00 SP == 10:00 Rule.
    """

    rule = SimpleIntervalRule(
        frequency=RecurrenceInterval.DAILY,
        start_date=AxiomDate.floating(
            datetime(2026, 1, 1, 10, 0, 0), "UTC"
        ),  # Naive (10am)
        interval=1,
    )

    # Input: 10:00 em SP (Aware)
    # Se convertesse para UTC, viraria "13:00". Se a regra usar 13:00, errou.
    # A regra deve usar o visual "10:00".
    sp_tz = ZoneInfo("America/Sao_Paulo")
    last_occ_sp = datetime(2026, 1, 1, 10, 0, 0, tzinfo=sp_tz)

    next_occurrence = rule.get_next_occurrence(last_occurrence=last_occ_sp)

    # Deve ser dia 02 às 10:00 Naive
    assert next_occurrence == datetime(2026, 1, 2, 10, 0, 0, tzinfo=ZoneInfo("UTC"))


def test_fixed_rule_sanitizes_naive_input() -> None:
    """
    Scenario: Fixed Task (UTC).
    Input: A Naive date (e.g., from a legacy part of the system or user error).
    Expected: The rule assumes the Naive date belongs to the rule's timezone (UTC).
    """

    # Regra Fixed (UTC) - Todo dia às 15:00 UTC
    rule = SimpleIntervalRule(
        frequency=RecurrenceInterval.DAILY,
        start_date=AxiomDate.fixed(datetime(2026, 1, 1, 15, 0, 0, tzinfo=UTC)),
        interval=1,
    )

    # Input Naive (15:00 sem fuso)
    input_naive = datetime(2026, 1, 1, 15, 0, 0)

    next_occurrence: datetime | None = rule.get_next_occurrence(
        last_occurrence=input_naive
    )

    # Deve retornar dia 02 às 15:00 UTC
    expected = datetime(2026, 1, 2, 15, 0, 0, tzinfo=UTC)

    assert next_occurrence is not None
    assert next_occurrence == expected

    tz_info: tzinfo | None = getattr(next_occurrence, "tzinfo", None)
    assert tz_info is not None
    assert tz_info == UTC


def test_check_end_conditions_logic_agnostic() -> None:
    """
    Verify that _check_end_conditions handles mixed types gracefully
    due to the sanitization logic.
    """

    # Regra Floating até dia 05/01 (Naive)
    end_date = AxiomDate.floating(datetime(2026, 1, 5, 10, 0, 0), "UTC")
    rule = SimpleIntervalRule(
        frequency=RecurrenceInterval.DAILY,
        start_date=AxiomDate.floating(datetime(2026, 1, 1, 10, 0, 0), "UTC"),
        end_date=end_date,
    )

    # Candidato Válido (Naive)
    valid_candidate = datetime(2026, 1, 4, 10, 0, 0)
    assert rule._check_end_conditions(valid_candidate) is True

    # Candidato Inválido (Naive)
    invalid_candidate = datetime(2026, 1, 6, 10, 0, 0)
    assert rule._check_end_conditions(invalid_candidate) is False

    # TESTE CRÍTICO: Passar um candidato AWARE para uma regra NAIVE.
    # O método _check_end_conditions deve lidar ou o chamador deve sanitizar.
    # Baseado na nossa correção, quem chama sanitiza,
    # mas vamos testar se o _get_closest_occurrence
    # (que chama o check) resolve isso.

    candidate_aware_valid = datetime(2026, 1, 4, 10, 0, 0, tzinfo=UTC)

    # Chamamos via public method para exercitar o fluxo completo
    # Se eu pedir a ocorrência DEPOIS do dia 4 (aware), ele deve achar o dia 5 (naive)
    # Se o check_end_conditions falhasse com TypeError, esse teste quebraria.
    res = rule.get_next_occurrence(last_occurrence=candidate_aware_valid)
    assert res == datetime(2026, 1, 5, 10, 0, 0, tzinfo=UTC)


def test_rrule_string_until_format_floating() -> None:
    """
    RFC 5545: Floating events MUST NOT have 'Z' in UNTIL.
    Format: YYYYMMDDThhmmss
    """

    rule = SimpleIntervalRule(
        frequency=RecurrenceInterval.DAILY,
        start_date=AxiomDate.floating(datetime(2026, 1, 1, 9, 0, 0), "UTC"),  # Naive
        end_date=AxiomDate.floating(datetime(2026, 12, 31, 23, 59, 59), "UTC"),  # Naive
    )

    rrule_str = rule.rrule_string

    # Verifica formato ISO sem separadores (padrão iCal) e SEM Z
    assert "UNTIL=20261231T235959" in rrule_str
    assert "Z" not in rrule_str.split("UNTIL=")[1]  # Garante que não tem Z no valor


def test_rrule_string_until_format_fixed() -> None:
    """
    RFC 5545: Fixed events (UTC) MUST have 'Z' in UNTIL.
    Format: YYYYMMDDThhmmssZ
    """

    rule = SimpleIntervalRule(
        frequency=RecurrenceInterval.DAILY,
        start_date=AxiomDate.fixed(datetime(2026, 1, 1, 9, 0, 0, tzinfo=UTC)),  # Aware
        end_date=AxiomDate.fixed(
            datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)
        ),  # Aware
    )

    rrule_str = rule.rrule_string

    # Verifica formato ISO com Z
    assert "UNTIL=20261231T235959Z" in rrule_str


# ============================================================
# Group 10: DST & Timezone Transitions (The "Wall Clock" Tests)
# ============================================================


def test_daily_recurrence_across_dst_spring_forward() -> None:
    """
    Scenario: In London (Europe/London), DST starts on March 29, 2026.
    Clocks jump from 01:00 to 02:00.
    A task at 09:00 AM should REMAIN at 09:00 AM local time.
    """

    # Start: Day before DST jump
    tz_name = "Europe/London"  # GMT (Offset +00:00)
    start_dt = datetime(2026, 3, 28, 9, 0)
    start = AxiomDate.floating(start_dt, tz_name)

    rule = SimpleIntervalRule(
        frequency=RecurrenceInterval.DAILY, start_date=start, interval=1
    )

    # First: March 28 @ 09:00 (GMT)
    occ1 = rule.get_next_occurrence()
    # Second: March 29 @ 09:00 (BST - British Summer Time / Offset +01:00)
    occ2 = rule.get_next_occurrence(occ1)

    assert occ1 == datetime(2026, 3, 28, 9, 0, tzinfo=ZoneInfo(tz_name))
    assert occ2 == datetime(2026, 3, 29, 9, 0, tzinfo=ZoneInfo(tz_name))

    # Crucial: If we materialize them with the timezone, they should both be 09:00
    assert start.materialize().hour == 9
    # The recurrence engine returns Naive for
    # Floating, so we check if the hour is preserved
    assert occ2 is not None
    assert occ2.hour == 9


def test_weekly_recurrence_across_dst_fallback() -> None:
    """
    Scenario: In New York (America/New_York), DST ends on Nov 1, 2026.
    Clocks jump back from 02:00 to 01:00.
    A weekly task on Mondays at 08:00 AM should stay at 08:00 AM.
    """

    tz_name = "America/New_York"
    # Oct 26 is Monday before DST end
    start_dt = datetime(2026, 10, 26, 8, 0)
    start = AxiomDate.floating(start_dt, tz_name)

    rule = WeeklyByDaysRule(start_date=start, days_of_week={0}, interval=1)  # Monday

    occ1 = rule.get_next_occurrence()
    occ2 = rule.get_next_occurrence(occ1)  # This crosses the DST boundary

    assert occ1 is not None
    assert occ1.date() == datetime(2026, 10, 26).date()
    assert occ1.hour == 8

    assert occ2 is not None
    assert occ2.date() == datetime(2026, 11, 2).date()
    assert occ2.hour == 8  # Still 08:00 AM Wall Clock


def test_fixed_rule_conversion_to_utc_consistency() -> None:
    """
    Verify that a FIXED rule (UTC-based) maintains its absolute instant
    even if the start_date was provided in a different timezone offset.
    """

    # 10:00 AM in Sao Paulo (UTC-3) is 01:00 PM UTC
    sp_tz = ZoneInfo("America/Sao_Paulo")
    local_dt = datetime(2026, 1, 1, 10, 0, tzinfo=sp_tz)

    # AxiomDate.fixed converts to UTC internally
    start = AxiomDate.fixed(local_dt)

    rule = SimpleIntervalRule(
        frequency=RecurrenceInterval.DAILY, start_date=start, interval=1
    )

    occ = rule.get_next_occurrence()

    assert occ is not None

    # Should be 13:00 UTC
    assert occ.tzinfo is not None
    assert occ.hour == 13
    assert occ.minute == 0
    assert occ.tzinfo == UTC


def test_recurrence_logic_with_microsecond_sanitization() -> None:
    """
    Ensure microsecond noise in datetimes doesn't leak into recurrence calculations
    or comparisons, which could cause "next_occurrence" to return the same day twice.
    """

    # Start date with microseconds
    start_dt = datetime(2026, 1, 1, 10, 0, 0, 999999)
    start = AxiomDate.floating(start_dt, "UTC")

    rule = SimpleIntervalRule(
        frequency=RecurrenceInterval.DAILY, start_date=start, interval=1
    )

    # The implementation should truncate or ignore microseconds
    occ1 = rule.get_next_occurrence()

    assert occ1 is not None
    assert occ1.microsecond == 0
    assert occ1 == datetime(2026, 1, 1, 10, 0, 0, tzinfo=ZoneInfo("UTC"))
