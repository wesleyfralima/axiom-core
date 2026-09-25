from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from c_application.utils.date_utils import (
    local_to_utc,
    normalize_datetime,
    utc_to_local,
)


def test_normalize_datetime_returns_none_on_empty_input() -> None:
    """Ensure normalize_datetime returns None when input is null or empty."""

    assert normalize_datetime(None) is None
    assert normalize_datetime("") is None


def test_normalize_datetime_assumes_end_of_day_when_only_date_provided() -> None:
    """
    Ensure YYYY-MM-DD input results in 23:59:00
    at the target timezone, converted to UTC.
    """

    date_str: str = "2026-01-20"
    tz: str = "America/Sao_Paulo"  # UTC-3

    # 2026-01-20 23:59:00 BRT -> 2026-01-21 02:59:00 UTC
    result: datetime | None = normalize_datetime(
        date_str, tz_local=tz, assume_end_of_day=True
    )

    assert result is not None

    assert result.hour == 2
    assert result.minute == 59
    assert result.day == 21
    assert result.tzinfo == UTC


def test_normalize_datetime_with_full_iso_string() -> None:
    """
    Ensure full ISO strings are correctly
    converted to UTC without overriding time.
    """

    date_str: str = "2026-01-20T10:00:00"
    tz: str = "America/Sao_Paulo"  # UTC-3

    # 10:00:00 BRT -> 13:00:00 UTC
    result: datetime | None = normalize_datetime(date_str, tz_local=tz)

    assert result is not None

    assert result.hour == 13
    assert result.minute == 0
    assert result.tzinfo == UTC


def test_local_to_utc_respects_existing_timezone() -> None:
    """Ensure local_to_utc does not override timezone if string already has offset."""

    # The string already has a +02:00 offset
    dt_with_tz = datetime.fromisoformat("2026-01-20T10:00:00+02:00")

    # tz_local "America/Sao_Paulo" must be ignored
    result = local_to_utc(dt_with_tz, tz_local="America/Sao_Paulo")

    assert result.hour == 8
    assert result.tzinfo == UTC


def test_utc_to_local_conversion() -> None:
    """Ensure UTC datetime is correctly shifted to local timezone."""

    utc_dt: datetime = datetime(2026, 1, 20, 12, 0, tzinfo=UTC)
    tz: str = "America/Sao_Paulo"  # UTC-3

    result: datetime | None = utc_to_local(utc_dt, tz_local=tz)

    assert result is not None

    assert result.hour == 9
    assert result.minute == 0
    assert result.tzinfo == ZoneInfo(tz)


def test_normalize_datetime_without_end_of_day() -> None:
    """Ensure normalize_datetime uses 00:00 if assume_end_of_day is False."""

    date_str: str = "2026-01-20"
    result: datetime | None = normalize_datetime(
        date_str, tz_local="UTC", assume_end_of_day=False
    )

    assert result is not None

    # Must return 2026-01-20 00:00:00 UTC
    assert result.hour == 0
    assert result.minute == 0
    assert result.tzinfo == UTC
