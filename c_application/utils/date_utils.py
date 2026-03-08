from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def adjust_date_semantics(
        dt_utc: Optional[datetime],
        is_floating: bool,
        user_tz_str: str
) -> Optional[datetime]:
    """Adjust date semantics based on task type.

    - If `is_floating=True`: Converts the UTC datetime to the user's local
      timezone and removes tzinfo, making it naive (wall-clock time).
      Example: 13:00 UTC -> 10:00 São Paulo (-3) -> 10:00 (naive).
    - If `is_floating=False`: Keeps the datetime in UTC (aware).

    Args:
        dt_utc (Optional[datetime]): The UTC datetime to adjust.
        is_floating (bool): Whether the task is floating or fixed.
        user_tz_str (str): IANA timezone string for the user.

    Returns:
        Optional[datetime]: Adjusted datetime, or None if input is None.
    """

    if not dt_utc:
        return None

    try:
        tz = ZoneInfo(user_tz_str)
    except ZoneInfoNotFoundError:
        tz = timezone.utc

    if is_floating:
        # Garante que dt_utc seja aware antes de converter para local
        temp_dt = dt_utc if dt_utc.tzinfo else dt_utc.replace(tzinfo=timezone.utc)
        local_dt = temp_dt.astimezone(tz)
        return local_dt.replace(tzinfo=None)

    # Para tarefas fixas, garante que o retorno seja sempre aware UTC
    if dt_utc.tzinfo is None:
        return dt_utc.replace(tzinfo=timezone.utc)

    return dt_utc.astimezone(timezone.utc)


def normalize_datetime(
        date_str: Optional[str],
        *,
        tz_local: str = "UTC",
        assume_end_of_day: bool = True,
) -> Optional[datetime]:
    """Normalize a date string into a datetime object.

    Interprets a date string in ISO format. If both date and time are
    provided, parses them directly. If only a date is provided, optionally
    assumes the end of the day (23:59).

    Args:
        date_str (Optional[str]): Date string in ISO format.
        tz_local (str, optional): Local timezone to apply. Defaults to "UTC".
        assume_end_of_day (bool, optional): Whether to assume 23:59 when only
            a date is provided. Defaults to True.

    Returns:
        Optional[datetime]: Normalized datetime in UTC, or None if input is None.
    """

    if not date_str:
        return None

    # 1. Initial parse
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        return None

    # 2. If only date (YYYY-MM-DD), adjust to end of day if requested
    if ("T" not in date_str and " " not in date_str) and assume_end_of_day:
        dt = dt.replace(hour=23, minute=59, second=0, microsecond=0)

    # 3. Convert to UTC
    # Se a string já veio com timezone, apenas converte para UTC
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc)

    # Caso contrário, trata como local e converte
    return local_to_utc(local_dt=dt, tz_local=tz_local)


def local_to_utc(local_dt: datetime, tz_local: str) -> datetime:
    """Convert a local datetime to UTC.

    Args:
        local_dt (datetime): Local datetime (naive or aware).
        tz_local (str): IANA timezone string to apply if naive.

    Returns:
        datetime: UTC-aware datetime.
    """

    try:
        local_tz_obj = ZoneInfo(tz_local)
    except ZoneInfoNotFoundError:
        local_tz_obj = timezone.utc

    # If datetime is naive, apply local timezone
    if local_dt.tzinfo is None:
        local_dt = local_dt.replace(tzinfo=local_tz_obj)

    return local_dt.astimezone(timezone.utc)


def utc_to_local(utc_dt: datetime, tz_local: str = "UTC") -> datetime:
    """Convert a UTC datetime to a local timezone.

    Args:
        utc_dt (datetime): UTC-aware datetime.
        tz_local (str, optional): Target IANA timezone string. Defaults to "UTC".

    Returns:
        datetime: Local timezone-aware datetime.
    """

    try:
        local_tz_obj = ZoneInfo(tz_local)
    except ZoneInfoNotFoundError:
        local_tz_obj = timezone.utc

    # If datetime is naive, apply local timezone
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)

    return utc_dt.astimezone(local_tz_obj)
