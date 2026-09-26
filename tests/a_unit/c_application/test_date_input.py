"""Dates as people type them, resolved against the user's today."""

from datetime import UTC, date, datetime, time

import pytest

from a_core.exceptions import InvalidValueError
from c_application.utils.date_input import (
    at_time,
    end_of_day,
    local_today,
    resolve_date_input,
    resolve_horizon,
)

TODAY = date(2026, 3, 5)


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("today", date(2026, 3, 5)),
        ("Tomorrow", date(2026, 3, 6)),
        ("yesterday", date(2026, 3, 4)),
        ("tomorrow 14:30", datetime(2026, 3, 6, 14, 30)),
        ("today  9:05", datetime(2026, 3, 5, 9, 5)),
        ("2026-10-01", date(2026, 10, 1)),
        ("2026-10-01 14:00", datetime(2026, 10, 1, 14, 0)),
        ("2026-10-01T14:00", datetime(2026, 10, 1, 14, 0)),
    ],
)
def test_resolve_date_input(typed: str, expected: date | datetime) -> None:
    assert resolve_date_input(typed, today=TODAY) == expected


def test_dates_and_datetimes_pass_through() -> None:
    moment = datetime(2026, 1, 1, 8, 0)
    assert resolve_date_input(moment, today=TODAY) is moment
    assert resolve_date_input(date(2026, 1, 1), today=TODAY) == date(2026, 1, 1)


@pytest.mark.parametrize(
    "typed", ["next friday", "tomorrow 25:00", "2026-13-01", "tomorrow at 9", ""]
)
def test_unknown_expressions_are_refused(typed: str) -> None:
    with pytest.raises(InvalidValueError, match="Invalid date"):
        resolve_date_input(typed, today=TODAY)


def test_at_time_only_fills_a_missing_time() -> None:
    assert at_time(date(2026, 3, 5), time(23, 59)) == datetime(2026, 3, 5, 23, 59)
    moment = datetime(2026, 3, 5, 8, 0)
    assert at_time(moment, time(23, 59)) is moment


def test_local_today_follows_the_time_zone() -> None:
    late_utc = datetime(2026, 3, 6, 1, 0, tzinfo=UTC)
    assert local_today(late_utc, "UTC") == date(2026, 3, 6)
    assert local_today(late_utc, "America/Sao_Paulo") == date(2026, 3, 5)


@pytest.mark.parametrize(
    ("ahead", "expected"),
    [
        (0, date(2026, 3, 5)),
        (7, date(2026, 3, 12)),
        ("10", date(2026, 3, 15)),
        ("2026-04-01", date(2026, 4, 1)),
        ("tomorrow", date(2026, 3, 6)),
        (date(2026, 5, 1), date(2026, 5, 1)),
    ],
)
def test_resolve_horizon(ahead: int | str | date, expected: date) -> None:
    assert resolve_horizon(ahead, today=TODAY) == expected


def test_a_negative_horizon_is_refused() -> None:
    with pytest.raises(InvalidValueError):
        resolve_horizon(-1, today=TODAY)


def test_a_wrong_horizon_mentions_both_forms() -> None:
    with pytest.raises(InvalidValueError, match="a number of days, or a date"):
        resolve_horizon("soon", today=TODAY)


def test_end_of_day_is_aware_in_the_zone() -> None:
    end = end_of_day(TODAY, "America/Sao_Paulo")
    assert (end.hour, end.minute) == (23, 59)
    assert end.astimezone(UTC) == datetime(2026, 3, 6, 2, 59, 59, tzinfo=UTC)
