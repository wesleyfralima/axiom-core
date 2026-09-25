from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo

import pytest

from a_core.exceptions import ValidationException
from b_domain.value_objects import DueDate
from b_domain.value_objects.dates import DateKind

UTC_TZ_OBJ: ZoneInfo = ZoneInfo("UTC")
SP_TZ_NAME: str = "America/Sao_Paulo"
NY_TZ_NAME: str = "America/New_York"


# ============================================================
# Group 1: Initialization and Validation
# ============================================================


def test_due_date_cant_accept_none() -> None:
    """Ensure DueDate accepts None and is not considered overdue."""

    with pytest.raises(ValidationException):
        _: DueDate = DueDate(
            # (value can't be None, but that's what we are testing)
            value=None,  # type: ignore
            timezone="America/Sao_Paulo",
            kind=DateKind.FIXED,
        )


def test_due_date_accepts_valid_floating_datetime() -> None:
    """Ensure DueDate accepts a valid floating (naive) datetime."""

    future_date: datetime = datetime.now() + timedelta(days=1)
    due_date: DueDate = DueDate.floating(
        dt=future_date,
        source_tz=SP_TZ_NAME,
    )

    assert due_date.value == future_date
    assert due_date.is_floating is True
    assert due_date.timezone == SP_TZ_NAME


def test_due_date_accepts_valid_fixed_datetime() -> None:
    """Ensure DueDate accepts a valid fixed (timezone-aware) datetime."""

    future_date: datetime = datetime.now(tz=UTC_TZ_OBJ) + timedelta(days=1)
    due_date: DueDate = DueDate.fixed(future_date)

    assert due_date.value == future_date
    assert due_date.is_floating is False
    assert due_date.timezone == "UTC"


def test_due_date_rejects_unrealistically_old_date() -> None:
    """Ensure DueDate rejects dates considered unrealistically old."""

    invalid_date: datetime = datetime(1999, 12, 31)

    with pytest.raises(ValidationException):
        DueDate.floating(invalid_date, source_tz="UTC")


def test_floating_due_date_rejects_timezone_aware_datetime() -> None:
    """Ensure floating due date rejects timezone-aware datetime."""

    aware_date: datetime = datetime.now(tz=UTC_TZ_OBJ)

    with pytest.raises(ValidationException):
        DueDate.floating(aware_date, source_tz="UTC")


def test_fixed_due_date_rejects_naive_datetime() -> None:
    """Ensure fixed due date rejects naive datetime."""

    naive_date: datetime = datetime.now()

    with pytest.raises(ValidationException):
        DueDate.fixed(naive_date)


def test_fixed_due_date_accepts_native_utc() -> None:
    """
    Ensure we can pass datetime.timezone.utc directly.
    """

    instant = datetime.now(tz=UTC)

    # This must pass now without errors
    due = DueDate.fixed(instant)

    assert due.timezone == "UTC"
    assert due.is_floating is False


# ============================================================
# Group 2: Materialization Logic
# ============================================================


def test_materialize_floating_uses_target_timezone() -> None:
    """Ensure floating due date materializes using target timezone."""

    date: datetime = datetime(2026, 1, 10, 9, 0, 0)

    due_date: DueDate = DueDate.floating(
        dt=date,
        source_tz=SP_TZ_NAME,
    )

    materialized: datetime | None = due_date.materialize("UTC")
    assert materialized is not None
    assert materialized.hour == 9

    tz_info: tzinfo | None = materialized.tzinfo
    assert tz_info is not None
    assert tz_info.tzname(None) == "UTC"


def test_materialize_floating_uses_own_timezone_when_no_target() -> None:
    """Ensure floating due date uses its own timezone when no target is provided."""

    date: datetime = datetime(2026, 1, 10, 9, 0, 0)

    due_date: DueDate = DueDate.floating(
        dt=date,
        source_tz=SP_TZ_NAME,
    )

    materialized: datetime | None = due_date.materialize()

    assert materialized is not None
    assert materialized.tzinfo is not None
    assert materialized.tzinfo.key == SP_TZ_NAME  # type: ignore[attr-defined]


def test_materialize_fixed_keeps_original_timezone() -> None:
    """Ensure fixed due date keeps original timezone when no target is provided."""

    instant: datetime = datetime(2026, 1, 10, 12, 0, 0, tzinfo=UTC_TZ_OBJ)

    due_date: DueDate = DueDate.fixed(instant)

    materialized: datetime | None = due_date.materialize()

    assert materialized == instant


def test_materialize_fixed_converts_timezone() -> None:
    """Ensure fixed due date converts correctly to target timezone."""

    instant: datetime = datetime(2026, 1, 10, 12, 0, 0, tzinfo=UTC_TZ_OBJ)

    due_date: DueDate = DueDate.fixed(instant)

    materialized: datetime | None = due_date.materialize(SP_TZ_NAME)

    assert materialized is not None
    assert materialized.tzinfo is not None
    assert materialized.tzinfo.key == SP_TZ_NAME  # type: ignore[attr-defined]
    assert materialized.hour == 9  # UTC-3


# ============================================================
# Group 3: Overdue Logic
# ============================================================


def test_floating_due_date_is_overdue_when_in_the_past() -> None:
    """Ensure floating due date is overdue when in the past."""

    past_date: datetime = datetime.now() - timedelta(days=1)

    due_date: DueDate = DueDate.floating(
        dt=past_date,
        source_tz="UTC",
    )

    now: datetime = datetime.now(tz=UTC_TZ_OBJ)

    assert due_date.is_overdue(now) is True


def test_floating_due_date_is_not_overdue_when_in_the_future() -> None:
    """Ensure floating due date is not overdue when in the future."""

    future_date: datetime = datetime.now() + timedelta(days=1)

    due_date: DueDate = DueDate.floating(
        dt=future_date,
        source_tz="UTC",
    )

    now: datetime = datetime.now(tz=UTC_TZ_OBJ)

    assert due_date.is_overdue(now) is False


def test_fixed_due_date_is_overdue_when_in_the_past() -> None:
    """Ensure fixed due date is overdue when instant has passed."""

    past_instant: datetime = datetime.now(tz=UTC_TZ_OBJ) - timedelta(days=1)

    due_date: DueDate = DueDate.fixed(past_instant)
    now: datetime = datetime.now(tz=UTC_TZ_OBJ)

    assert due_date.is_overdue(now) is True


def test_fixed_due_date_is_not_overdue_when_in_the_future() -> None:
    """Ensure fixed due date is not overdue when instant is in the future."""

    future_instant: datetime = datetime.now(tz=UTC_TZ_OBJ) + timedelta(days=1)

    due_date: DueDate = DueDate.fixed(future_instant)
    now: datetime = datetime.now(tz=UTC_TZ_OBJ)

    assert due_date.is_overdue(now) is False


def test_due_date_is_not_overdue_when_equal() -> None:
    """Ensure due date is not overdue when now equals due."""

    instant: datetime = datetime(2026, 1, 10, 12, 0, 0, tzinfo=UTC_TZ_OBJ)

    due_date: DueDate = DueDate.fixed(instant)

    assert due_date.is_overdue(instant) is False


def test_floating_due_date_compares_correctly_across_timezones() -> None:
    """Ensure floating due date compares correctly across timezones."""

    date: datetime = datetime(2026, 1, 10, 9, 0, 0)

    due_date: DueDate = DueDate.floating(
        dt=date,
        source_tz=SP_TZ_NAME,
    )

    now: datetime = datetime(2026, 1, 10, 12, 0, 1, tzinfo=UTC_TZ_OBJ)

    assert due_date.is_overdue(now) is True


def test_is_overdue_rejects_naive_now() -> None:
    """Ensure is_overdue rejects naive reference time."""

    future_date: datetime = datetime.now() + timedelta(days=1)

    due_date: DueDate = DueDate.floating(
        dt=future_date,
        source_tz="UTC",
    )

    with pytest.raises(ValidationException):
        due_date.is_overdue(datetime.now())


def test_is_overdue_rejects_custom_fixed_offsets() -> None:
    """
    Ensure is_overdue rejects reference time without IANA timezone or UTC.
    """

    future_date: datetime = datetime.now() + timedelta(days=1)

    # Any floating task
    due_date: DueDate = DueDate.floating(
        dt=future_date,
        source_tz="UTC",
    )

    # Try the overdue check with a clock in a manual timezone (invalid)
    invalid_tz = timezone(timedelta(hours=-5))
    now: datetime = datetime.now(tz=invalid_tz)

    with pytest.raises(ValidationException) as exc:
        due_date.is_overdue(now)

    assert "must use an IANA timezone or UTC" in str(exc.value)


# ============================================================
# Group 4: DST Semantics
# ============================================================


def test_floating_due_date_respects_dst_change() -> None:
    """Ensure floating due date preserves local time across DST changes."""

    date: datetime = datetime(2026, 3, 8, 9, 0, 0)  # 9 AM local

    due_date: DueDate = DueDate.floating(
        dt=date,
        source_tz=NY_TZ_NAME,
    )

    materialized: datetime | None = due_date.materialize(NY_TZ_NAME)

    assert materialized is not None
    assert materialized.hour == 9
    assert materialized.tzinfo is not None
    assert materialized.tzinfo.key == NY_TZ_NAME  # type: ignore[attr-defined]


# ============================================================
# Group 5: Immutability
# ============================================================


def test_due_date_is_immutable() -> None:
    """Ensure DueDate is immutable."""

    now_aware = datetime.now(tz=UTC)
    due_date: DueDate = DueDate.fixed(now_aware)

    with pytest.raises(FrozenInstanceError):
        due_date.value = datetime.now()  # type: ignore[misc]


def test_floating_due_date_uses_its_own_zone_not_the_zone_of_now() -> None:
    """Regression: 23:59 in São Paulo was read as 23:59 UTC (3 h early)."""

    due_date: DueDate = DueDate.floating(
        dt=datetime(2026, 9, 24, 23, 59), source_tz=SP_TZ_NAME
    )

    # 23:45 in São Paulo, expressed in UTC (the application clock)
    now: datetime = datetime(2026, 9, 25, 2, 45, tzinfo=UTC_TZ_OBJ)

    assert due_date.is_overdue(now) is False
    assert due_date.is_overdue(now + timedelta(minutes=15)) is True
