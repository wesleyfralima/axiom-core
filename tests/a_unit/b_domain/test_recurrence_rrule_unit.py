from datetime import UTC, date, datetime, time

from b_domain.value_objects import RecurrenceInterval
from b_domain.value_objects.dates import AxiomDate
from b_domain.value_objects.recurrences import (
    BusinessDayRule,
    HourlyWindowRule,
    MonthlyAllWeekdaysRule,
    MonthlyByDaysRule,
    MonthlyPositionalRule,
    MonthlyWeekdayPositionalRule,
    WeeklyByDaysRule,
)
from b_domain.value_objects.recurrences.simple import SimpleIntervalRule

# ============================================================


def test_hourly_window_rrule_floating_basic() -> None:
    """Should generate a standard RRULE string with BYHOUR for floating dates."""

    # Using floating factory: naive datetime + timezone string
    start = AxiomDate.floating(datetime(2026, 1, 1, 10, 0), "America/Sao_Paulo")

    rule = HourlyWindowRule(
        start_date=start, window_start=time(8, 0), window_end=time(14, 0), interval=3
    )

    # Starting from 8:00, interval 3: 8, 11, 14
    assert rule.rrule_string == "RRULE:FREQ=HOURLY;INTERVAL=3;BYHOUR=8,11,14"


def test_hourly_window_rrule_fixed_with_until() -> None:
    """Should generate RRULE with UNTIL in UTC format for fixed dates."""

    # Using fixed factory: aware datetime
    dt_start = datetime(2026, 5, 1, 10, 0, tzinfo=UTC)
    dt_end = datetime(2026, 5, 2, 23, 59, tzinfo=UTC)

    rule = HourlyWindowRule(
        start_date=AxiomDate.fixed(dt_start),
        end_date=AxiomDate.fixed(dt_end),
        window_start=time(10, 0),
        window_end=time(12, 0),
        interval=1,
    )

    # UNTIL must end with 'Z' for fixed (UTC) dates
    assert "UNTIL=20260502T235900Z" in rule.rrule_string
    assert "BYHOUR=10,11,12" in rule.rrule_string


def test_hourly_window_rrule_with_count() -> None:
    """Should include COUNT instead of UNTIL when count is provided."""

    start = AxiomDate.floating(datetime(2026, 1, 1, 8, 0), "UTC")

    rule = HourlyWindowRule(
        start_date=start,
        window_start=time(8, 0),
        window_end=time(10, 0),
        interval=1,
        count=5,
    )

    assert "COUNT=5" in rule.rrule_string
    assert "UNTIL" not in rule.rrule_string


def test_hourly_window_single_hour_window() -> None:
    """
    Should generate BYHOUR with a single value
    if window and interval only allow one.
    """

    start = AxiomDate.floating(datetime(2026, 1, 1, 8, 0), "Europe/London")

    rule = HourlyWindowRule(
        start_date=start,
        window_start=time(10, 0),
        window_end=time(12, 0),
        interval=5,  # Interval larger than the window duration
    )

    # Only the window_start fits
    assert "BYHOUR=10" in rule.rrule_string


def test_hourly_window_interval_skipping_end() -> None:
    """Should not include window_end in BYHOUR if interval skips over it."""

    start = AxiomDate.floating(datetime(2026, 1, 1, 8, 0), "UTC")

    rule = HourlyWindowRule(
        start_date=start, window_start=time(8, 0), window_end=time(10, 0), interval=3
    )

    # 8 + 3 = 11, which is > window_end (10). So only 8 should be present.
    assert "BYHOUR=8" in rule.rrule_string


# ============================================================
# Group 2: MonthlyByDaysRule
# ============================================================


def test_monthly_by_days_rrule_basic() -> None:
    """Should generate a MONTHLY RRULE with sorted BYMONTHDAY."""

    start = AxiomDate.floating(datetime(2026, 1, 1, 10, 0), "America/Sao_Paulo")

    # Using a set to ensure order is handled by the implementation
    rule = MonthlyByDaysRule(start_date=start, days_of_month={20, 1, 10}, interval=1)
    # Implementation must sort days: 1, 10, 20
    assert rule.rrule_string == "RRULE:FREQ=MONTHLY;BYMONTHDAY=1,10,20"


def test_monthly_by_days_rrule_with_interval() -> None:
    """Should include INTERVAL when greater than 1."""

    start = AxiomDate.floating(datetime(2026, 1, 1, 9, 0), "UTC")
    rule = MonthlyByDaysRule(start_date=start, days_of_month={15}, interval=3)
    assert rule.rrule_string == "RRULE:FREQ=MONTHLY;INTERVAL=3;BYMONTHDAY=15"


def test_monthly_by_days_rrule_with_count() -> None:
    """Should include COUNT in the monthly rule."""

    start = AxiomDate.floating(datetime(2026, 1, 1, 8, 0), "UTC")
    rule = MonthlyByDaysRule(start_date=start, days_of_month={1, 31}, count=12)
    assert "COUNT=12" in rule.rrule_string
    assert "BYMONTHDAY=1,31" in rule.rrule_string


def test_monthly_by_days_rrule_fixed_until() -> None:
    """Should format UNTIL correctly for fixed (UTC) start dates."""

    dt_start = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    dt_end = datetime(2027, 1, 1, 12, 0, tzinfo=UTC)

    rule = MonthlyByDaysRule(
        start_date=AxiomDate.fixed(dt_start),
        end_date=AxiomDate.fixed(dt_end),
        days_of_month={5},
    )
    # UNTIL should be in Zulu format[cite: 1]
    assert "UNTIL=20270101T120000Z" in rule.rrule_string


def test_monthly_by_days_edge_case_31() -> None:
    """Should correctly handle the last day of the month (31) in the string."""

    start = AxiomDate.floating(datetime(2026, 1, 31, 10, 0), "Europe/Berlin")
    rule = MonthlyByDaysRule(start_date=start, days_of_month={31})
    # Note: RFC 5545 ignores days that don't exist in specific months (like Feb 31),
    # but the RRULE string itself just lists the requested day.
    assert "BYMONTHDAY=31" in rule.rrule_string


# ============================================================
# Group 3: MonthlyPositionalRule
# ============================================================


def test_monthly_positional_last_day_rrule() -> None:
    """Should generate RRULE for the last day of the month using -1."""

    start = AxiomDate.floating(datetime(2026, 1, 31, 10, 0), "America/Sao_Paulo")
    rule = MonthlyPositionalRule(
        start_date=start,
        set_pos=-1,
        interval=1,  # Last day of month[cite: 4]
    )
    # The implementation maps set_pos directly to BYMONTHDAY[cite: 4]
    assert rule.rrule_string == "RRULE:FREQ=MONTHLY;BYMONTHDAY=-1"


def test_monthly_positional_specific_day_from_end() -> None:
    """Should generate RRULE for a specific day counting from the end."""

    start = AxiomDate.floating(datetime(2026, 1, 1, 9, 0), "UTC")
    rule = MonthlyPositionalRule(
        start_date=start,
        set_pos=-5,
        interval=2,  # 5th day from the end[cite: 4]
    )
    assert rule.rrule_string == "RRULE:FREQ=MONTHLY;INTERVAL=2;BYMONTHDAY=-5"


def test_monthly_positional_first_day_rrule() -> None:
    """Should generate RRULE for the first day of the month using 1."""

    start = AxiomDate.floating(datetime(2026, 1, 1, 8, 0), "Europe/Lisbon")
    rule = MonthlyPositionalRule(
        start_date=start,
        set_pos=1,
        count=10,  # 1st day of month[cite: 4]
    )
    assert "FREQ=MONTHLY" in rule.rrule_string
    assert "BYMONTHDAY=1" in rule.rrule_string
    assert "COUNT=10" in rule.rrule_string


def test_monthly_positional_fixed_until() -> None:
    """Should format UNTIL correctly for fixed (UTC) dates in positional rules."""

    dt_start = datetime(2026, 3, 15, 14, 0, tzinfo=UTC)
    dt_end = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)

    rule = MonthlyPositionalRule(
        start_date=AxiomDate.fixed(dt_start),
        end_date=AxiomDate.fixed(dt_end),
        set_pos=-1,
    )
    # Fixed dates materialize as UTC 'Z' strings[cite: 1]
    assert "UNTIL=20261231T235900Z" in rule.rrule_string
    assert "BYMONTHDAY=-1" in rule.rrule_string


def test_monthly_positional_large_positive_index() -> None:
    """Should generate RRULE for a large positive positional index."""

    start = AxiomDate.floating(datetime(2026, 1, 1, 10, 0), "UTC")
    rule = MonthlyPositionalRule(
        start_date=start,
        set_pos=31,  # Max allowed value[cite: 4]
    )
    assert "BYMONTHDAY=31" in rule.rrule_string


# ============================================================
# Group 4: MonthlyWeekdayPositionalRule
# ============================================================


def test_monthly_weekday_positional_rrule_basic() -> None:
    """Should generate RRULE for the first Monday of the month."""

    start = AxiomDate.floating(datetime(2026, 1, 1, 10, 0), "America/Sao_Paulo")
    rule = MonthlyWeekdayPositionalRule(
        start_date=start,
        days_of_week={0},  # Monday[cite: 5]
        set_pos=1,  # First occurrence[cite: 5]
        interval=1,
    )
    # Expected format: FREQ=MONTHLY;BYDAY=1MO[cite: 5]
    assert rule.rrule_string == "RRULE:FREQ=MONTHLY;BYDAY=1MO"


def test_monthly_weekday_positional_last_friday() -> None:
    """Should generate RRULE for the last Friday of the month."""

    start = AxiomDate.floating(datetime(2026, 1, 1, 9, 0), "UTC")
    rule = MonthlyWeekdayPositionalRule(
        start_date=start,
        days_of_week={4},  # Friday[cite: 5]
        set_pos=-1,  # Last occurrence[cite: 5]
        interval=1,
    )
    assert "BYDAY=-1FR" in rule.rrule_string


def test_monthly_weekday_positional_multiple_days() -> None:
    """Should generate RRULE for the second Monday and Wednesday."""

    start = AxiomDate.floating(datetime(2026, 1, 1, 8, 0), "UTC")
    rule = MonthlyWeekdayPositionalRule(
        start_date=start,
        days_of_week={0, 2},  # Monday (0) and Wednesday (2)[cite: 5]
        set_pos=2,  # Second occurrence[cite: 5]
    )
    # Implementation sorts days_of_week before joining[cite: 5]
    assert "BYDAY=2MO,2WE" in rule.rrule_string


def test_monthly_weekday_positional_with_interval_and_count() -> None:
    """Should include interval and count in the positional rule."""

    start = AxiomDate.floating(datetime(2026, 1, 1, 10, 0), "Europe/London")
    rule = MonthlyWeekdayPositionalRule(
        start_date=start,
        days_of_week={1},  # Tuesday[cite: 5]
        set_pos=3,  # Third occurrence[cite: 5]
        interval=3,
        count=5,
    )
    assert "INTERVAL=3" in rule.rrule_string
    assert "COUNT=5" in rule.rrule_string
    assert "BYDAY=3TU" in rule.rrule_string


def test_monthly_weekday_positional_fixed_until() -> None:
    """Should format UNTIL correctly for fixed dates in positional weekday rules."""

    dt_start = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    dt_end = datetime(2027, 6, 1, 12, 0, tzinfo=UTC)

    rule = MonthlyWeekdayPositionalRule(
        start_date=AxiomDate.fixed(dt_start),
        end_date=AxiomDate.fixed(dt_end),
        days_of_week={6},  # Sunday[cite: 5]
        set_pos=-1,  # Last occurrence[cite: 5]
    )
    # Fixed dates must result in Zulu time string[cite: 1]
    assert "UNTIL=20270601T120000Z" in rule.rrule_string
    assert "BYDAY=-1SU" in rule.rrule_string


# ============================================================
# Group 5: MonthlyAllWeekdaysRule
# ============================================================


def test_monthly_all_weekdays_rrule_basic() -> None:
    """Should generate RRULE for all occurrences of specific weekdays in a month."""

    start = AxiomDate.floating(datetime(2026, 1, 1, 10, 0), "America/Sao_Paulo")
    rule = MonthlyAllWeekdaysRule(
        start_date=start,
        days_of_week={0, 4},
        interval=1,  # Monday and Friday[cite: 6]
    )
    # Expected format: FREQ=MONTHLY;BYDAY=MO,FR (sorted)[cite: 6]
    assert rule.rrule_string == "RRULE:FREQ=MONTHLY;BYDAY=MO,FR"


def test_monthly_all_weekdays_rrule_with_interval() -> None:
    """Should include INTERVAL when repeating every N months."""

    start = AxiomDate.floating(datetime(2026, 1, 1, 9, 0), "UTC")
    rule = MonthlyAllWeekdaysRule(
        start_date=start,
        days_of_week={2},
        interval=2,  # Wednesday[cite: 6]
    )
    assert rule.rrule_string == "RRULE:FREQ=MONTHLY;INTERVAL=2;BYDAY=WE"


def test_monthly_all_weekdays_rrule_with_count() -> None:
    """Should include COUNT in the rule string."""

    start = AxiomDate.floating(datetime(2026, 1, 1, 8, 0), "UTC")
    rule = MonthlyAllWeekdaysRule(
        start_date=start,
        days_of_week={0, 1, 2, 3, 4},  # All business days[cite: 6]
        count=20,
    )
    assert "COUNT=20" in rule.rrule_string
    assert "BYDAY=MO,TU,WE,TH,FR" in rule.rrule_string


def test_monthly_all_weekdays_fixed_until() -> None:
    """Should format UNTIL correctly for fixed dates."""

    dt_start = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    dt_end = datetime(2026, 6, 1, 23, 59, tzinfo=UTC)

    rule = MonthlyAllWeekdaysRule(
        start_date=AxiomDate.fixed(dt_start),
        end_date=AxiomDate.fixed(dt_end),
        days_of_week={5, 6},  # Weekends[cite: 6]
    )
    # UNTIL should be Zulu format for fixed dates[cite: 1]
    assert "UNTIL=20260601T235900Z" in rule.rrule_string
    assert "BYDAY=SA,SU" in rule.rrule_string


def test_monthly_all_weekdays_single_day_sort() -> None:
    """Should ensure weekdays are always sorted in the output string."""

    start = AxiomDate.floating(datetime(2026, 1, 1, 10, 0), "UTC")
    # Input out of order: Sunday (6), Monday (0)[cite: 6]
    rule = MonthlyAllWeekdaysRule(start_date=start, days_of_week={6, 0})
    # Output must be MO,SU[cite: 6]
    assert "BYDAY=MO,SU" in rule.rrule_string


# ============================================================
# Group 6: SimpleIntervalRule
# ============================================================


def test_simple_interval_daily_floating() -> None:
    """Should generate a basic DAILY RRULE with floating date."""

    start = AxiomDate.floating(datetime(2026, 1, 1, 8, 0), "America/Sao_Paulo")
    rule = SimpleIntervalRule(
        start_date=start, frequency=RecurrenceInterval.DAILY, interval=3
    )
    # FREQ is mapped from the enum[cite: 7]
    assert rule.rrule_string == "RRULE:FREQ=DAILY;INTERVAL=3"


def test_simple_interval_weekly_with_count() -> None:
    """Should generate a WEEKLY RRULE including the COUNT attribute."""

    start = AxiomDate.floating(datetime(2026, 1, 1, 10, 0), "UTC")
    rule = SimpleIntervalRule(
        start_date=start, frequency=RecurrenceInterval.WEEKLY, interval=1, count=10
    )
    assert rule.rrule_string == "RRULE:FREQ=WEEKLY;COUNT=10"


def test_simple_interval_monthly_fixed_until() -> None:
    """Should generate a MONTHLY RRULE with a UTC (fixed) UNTIL date."""

    dt_start = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    dt_end = datetime(2026, 12, 1, 12, 0, tzinfo=UTC)

    rule = SimpleIntervalRule(
        start_date=AxiomDate.fixed(dt_start),
        end_date=AxiomDate.fixed(dt_end),
        frequency=RecurrenceInterval.MONTHLY,
        interval=1,
    )
    # Fixed dates must result in Zulu 'Z' format[cite: 1]
    assert "FREQ=MONTHLY" in rule.rrule_string
    assert "UNTIL=20261201T120000Z" in rule.rrule_string


def test_simple_interval_yearly_floating_until() -> None:
    """Should generate a YEARLY RRULE with a floating UNTIL date."""

    start = AxiomDate.floating(datetime(2026, 1, 1, 9, 0), "Europe/Paris")
    end = AxiomDate.floating(datetime(2030, 1, 1, 9, 0), "Europe/Paris")

    rule = SimpleIntervalRule(
        start_date=start, end_date=end, frequency=RecurrenceInterval.YEARLY, interval=2
    )
    # Floating dates do not have the 'Z' suffix[cite: 1]
    assert "FREQ=YEARLY;INTERVAL=2" in rule.rrule_string
    assert "UNTIL=20300101T090000" in rule.rrule_string
    assert "Z" not in rule.rrule_string.split("UNTIL=")[1]


def test_simple_interval_hourly_basic() -> None:
    """Should generate an HOURLY RRULE string."""

    start = AxiomDate.fixed(datetime(2026, 1, 1, 0, 0, tzinfo=UTC))
    rule = SimpleIntervalRule(
        start_date=start, frequency=RecurrenceInterval.HOURLY, interval=6
    )
    assert rule.rrule_string == "RRULE:FREQ=HOURLY;INTERVAL=6"


# ============================================================
# Group 7: WeeklyByDaysRule
# ============================================================


def test_weekly_by_days_rrule_basic() -> None:
    """Should generate a basic WEEKLY RRULE with specific weekdays."""

    # Using floating date for local time representation[cite: 1]
    start = AxiomDate.floating(datetime(2026, 1, 1, 10, 0), "America/Sao_Paulo")
    rule = WeeklyByDaysRule(
        start_date=start,
        days_of_week={0, 2, 4},  # Monday, Wednesday, Friday[cite: 8]
        interval=1,
    )
    # The weekdays must be sorted in the output string[cite: 8]
    assert rule.rrule_string == "RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR"


def test_weekly_by_days_with_interval_and_count() -> None:
    """Should include INTERVAL and COUNT in the weekly rule."""

    start = AxiomDate.floating(datetime(2026, 1, 1, 9, 0), "UTC")
    rule = WeeklyByDaysRule(
        start_date=start,
        days_of_week={1, 3},  # Tuesday, Thursday[cite: 8]
        interval=2,
        count=5,
    )
    assert "FREQ=WEEKLY" in rule.rrule_string
    assert "INTERVAL=2" in rule.rrule_string
    assert "COUNT=5" in rule.rrule_string
    assert "BYDAY=TU,TH" in rule.rrule_string


def test_weekly_by_days_fixed_until() -> None:
    """Should format UNTIL correctly with 'Z' for fixed start dates."""

    # Using fixed factory for UTC-aware datetime[cite: 1]
    dt_start = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    dt_end = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)

    rule = WeeklyByDaysRule(
        start_date=AxiomDate.fixed(dt_start),
        end_date=AxiomDate.fixed(dt_end),
        days_of_week={6},  # Sunday[cite: 8]
    )
    # UNTIL must match the start_date's fixed nature[cite: 1]
    assert "UNTIL=20260601T120000Z" in rule.rrule_string
    assert "BYDAY=SU" in rule.rrule_string


def test_weekly_by_days_all_week() -> None:
    """Should generate a BYDAY string containing all days of the week."""

    start = AxiomDate.floating(datetime(2026, 1, 1, 8, 0), "Europe/Berlin")
    rule = WeeklyByDaysRule(
        start_date=start,
        days_of_week={0, 1, 2, 3, 4, 5, 6},  # All days[cite: 8]
    )
    assert "BYDAY=MO,TU,WE,TH,FR,SA,SU" in rule.rrule_string


def test_weekly_by_days_sorting_check() -> None:
    """Should ensure weekdays are sorted regardless of input order."""

    start = AxiomDate.floating(datetime(2026, 1, 1, 10, 0), "UTC")
    # Input provided out of order[cite: 8]
    rule = WeeklyByDaysRule(start_date=start, days_of_week={6, 0, 3})
    # Output must be Monday, Thursday, Sunday[cite: 8]
    assert "BYDAY=MO,TH,SU" in rule.rrule_string


# ============================================================
# Group 8: BusinessDayRule
# ============================================================


def test_business_day_rrule_string_is_always_empty() -> None:
    """
    Should always return an empty string for rrule_string.
    RFC 5545 does not support business days natively[cite: 9].
    """

    # Mocking a simple business day checker (all days are business days)
    def is_workday(_: date) -> bool:
        return True

    start = AxiomDate.floating(datetime(2026, 1, 1, 9, 0), "America/Sao_Paulo")

    rule = BusinessDayRule(
        start_date=start,
        nth_day=5,
        is_business_day=is_workday,  # 5th business day
    )

    # The requirement is to return empty to signal non-compatibility[cite: 9]
    assert rule.rrule_string == ""


def test_business_day_supports_native_sync_is_false() -> None:
    """
    Should return False for native sync support[cite: 9].
    """

    def is_workday(d: date) -> bool:
        return d.weekday() < 5  # Only Mon-Fri

    start = AxiomDate.fixed(datetime(2026, 1, 1, 10, 0, tzinfo=UTC))

    rule = BusinessDayRule(
        start_date=start,
        nth_day=-1,
        is_business_day=is_workday,  # Last business day
    )

    assert rule.supports_native_sync() is False


def test_business_day_rrule_string_with_various_configs() -> None:
    """
    Ensures that regardless of interval, count or nth_day, the string remains empty.
    """

    def is_workday(_: date) -> bool:
        return True

    start = AxiomDate.floating(datetime(2026, 1, 1, 8, 0), "UTC")

    rule_a = BusinessDayRule(
        start_date=start, nth_day=1, interval=2, is_business_day=is_workday
    )

    rule_b = BusinessDayRule(
        start_date=start, nth_day=-1, count=10, is_business_day=is_workday
    )

    assert rule_a.rrule_string == ""
    assert rule_b.rrule_string == ""
