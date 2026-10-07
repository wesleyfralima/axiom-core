"""Dates as people type them: "2026-10-01", "tomorrow 14:00", "today", "12-25".

Every use case that receives a date from the user takes a ``DateInput`` and
resolves it here, relative to the user's "today" (their time zone, the
injected clock). A value without a time of day stays a ``date``: the caller
decides which time it gets (the user's default due time, the end of the day…).

New expressions ("next friday", "in 3 days", other languages) belong in
``_DAY_OFFSETS`` or next to it — the callers do not change.
"""

import re
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from a_core.exceptions import InvalidValueError

type DateInput = datetime | date | str
"""A datetime, a date without time, or a text expression to resolve."""

_DAY_OFFSETS: dict[str, int] = {
    "yesterday": -1,
    "today": 0,
    "tomorrow": 1,
}
"""Words for a day, as an offset from today."""

_ACCEPTED: str = (
    "YYYY-MM-DD, MM-DD (the next one), YYYY-MM-DD HH:MM, "
    "today, tomorrow or yesterday (+ HH:MM), HH:MM (today)"
)

_TIME_RE: re.Pattern[str] = re.compile(r"^(\d{1,2}):(\d{2})$")

_MONTH_DAY_RE: re.Pattern[str] = re.compile(r"^(\d{1,2})-(\d{1,2})$")


def local_today(now: datetime, tz_name: str) -> date:
    """The user's calendar day at ``now``.

    Args:
        now (datetime): The current instant (naive values are read as UTC).
        tz_name (str): The user's IANA time zone.

    Returns:
        date: Today, where the user is.
    """
    aware: datetime = now if now.tzinfo else now.replace(tzinfo=UTC)
    try:
        return aware.astimezone(ZoneInfo(tz_name)).date()
    except (ZoneInfoNotFoundError, ValueError):
        return aware.astimezone(UTC).date()


def resolve_date_input(value: DateInput, *, today: date) -> date | datetime:
    """Turn what the user typed into a date or a datetime.

    Args:
        value (DateInput): A datetime (kept as it is), a date (kept: no time
            was given) or a text: an ISO date (``2026-10-01``), an ISO date
            and time (``2026-10-01 14:00`` or with ``T``), a month and day
            (``12-25``: the next one, today included), or a day word
            (``today``, ``tomorrow``, ``yesterday``); a month and day or a
            day word can be followed by ``HH:MM``, and ``HH:MM`` alone is
            today at that time.
        today (date): The user's today, which the words are relative to.

    Returns:
        date | datetime: A ``date`` when no time was given, else a naive
        ``datetime`` (wall-clock time; the caller knows the time zone).

    Raises:
        InvalidValueError: If the text is none of the accepted forms.
    """
    if isinstance(value, datetime | date):
        return value

    text: str = " ".join(value.strip().lower().split())
    parts: list[str] = text.split(" ")
    day_word, clock = parts[0], parts[1:]

    if not clock and _TIME_RE.match(day_word):
        # A time alone is today's
        return datetime.combine(today, _parse_clock(day_word, value))

    day: date | None = None
    if day_word in _DAY_OFFSETS:
        day = today + timedelta(days=_DAY_OFFSETS[day_word])
    elif match := _MONTH_DAY_RE.match(day_word):
        day = _next_month_day(int(match.group(1)), int(match.group(2)), today, value)
    if day is not None:
        if len(clock) > 1:
            raise _invalid(value)
        return datetime.combine(day, _parse_clock(clock[0], value)) if clock else day

    try:
        if len(text) == 10:
            return date.fromisoformat(text)
        parsed: datetime = datetime.fromisoformat(text)
    except ValueError:
        raise _invalid(value) from None
    return parsed


def at_time(value: date | datetime, clock: time) -> datetime:
    """A date with no time of day gets ``clock``; a datetime stays as it is."""
    if isinstance(value, datetime):
        return value
    return datetime.combine(value, clock)


def resolve_horizon(ahead: int | DateInput, *, today: date) -> date:
    """The last day a list looks ahead to.

    Args:
        ahead (int | DateInput): A number of days from today, or a date
            (a text is resolved like any date; its time, if any, is ignored).
        today (date): The user's today.

    Returns:
        date: The last day included.

    Raises:
        InvalidValueError: If the number is negative or the text is not a date.
    """
    if isinstance(ahead, int):
        if ahead < 0:
            raise InvalidValueError(concept="days ahead", invalid_value=str(ahead))
        return today + timedelta(days=ahead)
    if isinstance(ahead, str) and ahead.strip().isdigit():
        return today + timedelta(days=int(ahead))

    try:
        resolved: date | datetime = resolve_date_input(ahead, today=today)
    except InvalidValueError:
        raise InvalidValueError(
            concept="days ahead",
            invalid_value=str(ahead),
            valid_options=[f"a number of days, or a date ({_ACCEPTED})"],
        ) from None
    return resolved.date() if isinstance(resolved, datetime) else resolved


def local_instant(moment: datetime, tz_name: str) -> datetime:
    """A wall-clock time where the user is as an instant (aware); an aware
    one stays as it is."""
    if moment.tzinfo is not None:
        return moment
    try:
        zone: ZoneInfo = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo("UTC")
    return moment.replace(tzinfo=zone)


def end_of_day(day: date, tz_name: str) -> datetime:
    """The last instant of ``day`` where the user is (aware)."""
    try:
        zone: ZoneInfo = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo("UTC")
    return datetime.combine(day, time(23, 59, 59), tzinfo=zone)


def _next_month_day(month: int, day: int, today: date, original: str) -> date:
    """The next ``month``/``day`` from ``today`` on (29 February: a leap year)."""
    for year in range(today.year, today.year + 9):
        try:
            candidate: date = date(year, month, day)
        except ValueError:
            if (month, day) == (2, 29):
                continue
            raise _invalid(original) from None
        if candidate >= today:
            return candidate
    raise _invalid(original)


def _parse_clock(text: str, original: str) -> time:
    match: re.Match[str] | None = _TIME_RE.match(text)
    if not match:
        raise _invalid(original)
    try:
        return time(int(match.group(1)), int(match.group(2)))
    except ValueError:
        raise _invalid(original) from None


def _invalid(value: str) -> InvalidValueError:
    return InvalidValueError(
        concept="date", invalid_value=value, valid_options=[_ACCEPTED]
    )
