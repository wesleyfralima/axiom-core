import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, tzinfo
from datetime import timezone as dt_timezone
from enum import StrEnum
from typing import Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from a_core.exceptions import ValidationException

# TYPES
type TimezoneLike = dt_timezone | ZoneInfo
type TimezoneInput = dt_timezone | ZoneInfo | tzinfo | str


class DateKind(StrEnum):
    """
    Define the semantic nature of a date.

    Attributes:
        FIXED: An absolute instant in time (e.g., "Global Meeting at 14:00 UTC").
        FLOATING: A local clock time, independent of timezone
            (e.g., "Wake up at 07:00 AM").
    """

    FIXED = "fixed"  # An absolute instant (e.g., Global Meeting at 14:00 UTC)
    FLOATING = "floating"  # A local clock time (e.g., Wake up at 07:00 AM)


@dataclass(frozen=True, order=True)
class AxiomDate:
    """
    Universal temporal primitive for the Axiom ecosystem.
    Replaces raw `datetime` usage to ensure consistent timezone handling.

    Attributes:
        value (datetime): The underlying datetime value.
            - If FIXED: must be timezone-aware (preferably UTC).
            - If FLOATING: must be naive.
        kind (DateKind): Defines whether the date is FIXED or FLOATING.
        timezone (Optional[str]): The IANA timezone identifier ("America/Sao_Paulo").
            - For FLOATING: required, used as the anchor to interpret the local time
              and handle Daylight Saving Time (DST).
            - For FIXED: optional, used as preferred display timezone.
    """

    # Value is used for ordering (sorting) and
    # must be consistent with kind.
    value: datetime

    kind: DateKind = field(compare=False)

    # Timezone anchor or preferred display zone
    timezone: str | None = field(default=None, compare=False)
    """
    The IANA timezone identifier (e.g., "America/Sao_Paulo")
    used as the anchor to interpret floating dates and handle
    Daylight Saving Time (DST) changes accurately.
    """

    def __post_init__(self) -> None:
        """Ensure data integrity upon creation."""

        if self.value is None:
            raise ValidationException("'value' can't be None")

        # Validation for Floating dates
        if self.kind == DateKind.FLOATING:
            if self.value.tzinfo is not None:
                raise ValidationException("Floating dates must store a naive datetime.")
            if not self.timezone:
                raise ValidationException(
                    "Floating dates require a valid timezone name."
                )
            try:
                ZoneInfo(self.timezone)
            except ZoneInfoNotFoundError as e:
                raise ValidationException("Invalid timezone for floating date") from e

        # Validation for Fixed dates
        elif self.kind == DateKind.FIXED:
            if self.value.tzinfo is None:
                raise ValidationException(
                    "Fixed dates must store a timezone-aware datetime."
                )
            # Normalize to UTC for consistency
            object.__setattr__(self, "value", self.value.astimezone(UTC))

        self._extra_validation()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extra_validation(self) -> None:
        """Hook for subclasses performing extra validation."""

    # ------------------------------------------------------------------
    # Factories (Static Constructors)
    # ------------------------------------------------------------------

    @classmethod
    def fixed(cls, dt: datetime) -> Self:
        """Create a fixed AxiomDate.

        Args:
            dt (datetime): A timezone-aware datetime representing the fixed instant.

        Returns:
            AxiomDate: A fixed date instance normalized to UTC.

        Raises:
            ValidationException: If the datetime is naive (missing timezone info).
        """
        return cls(
            value=dt,
            kind=DateKind.FIXED,
            timezone="UTC",  # Timezone for fixed dates
        )

    @classmethod
    def floating(cls, dt: datetime, source_tz: str) -> Self:
        """Create a floating AxiomDate.

        Args:
            dt (datetime): Naive datetime representing the floating time.
            source_tz (str): IANA timezone identifier (e.g., "America/Sao_Paulo").

        Returns:
            AxiomDate: A floating date instance anchored to the given timezone.

        Raises:
            ValidationException: If the datetime is
                timezone-aware or the timezone is invalid.
        """
        return cls(
            value=dt,
            kind=DateKind.FLOATING,
            timezone=source_tz,
        )

    @classmethod
    def now(cls) -> "AxiomDate":
        """Convenient factory to create 'now' as a fixed date in UTC."""
        return cls.fixed(datetime.now(UTC))

    @classmethod
    def from_params(
        cls,
        dt: datetime,
        is_floating: bool,
        tz_name: str,
    ) -> Self:
        """Build an AxiomDate from params.

        Args:
            dt (datetime): A datetime representing date.
            is_floating (bool): Whether the date represented
                as a floating date. If false, it is fixed.
            tz_name (str): The timezone identifier.
        """

        if is_floating:
            return cls.floating(dt.replace(tzinfo=None), tz_name)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo(tz_name))

        return cls.fixed(dt.astimezone(UTC))

    # ------------------------------------------------------------------
    # Useful checks
    # ------------------------------------------------------------------

    @property
    def is_floating(self) -> bool:
        """Check if this AxiomDate is floating (local clock time)."""
        return self.kind == DateKind.FLOATING

    @property
    def is_fixed(self) -> bool:
        """Check if this AxiomDate is fixed (absolute instant in UTC)."""
        return self.kind == DateKind.FIXED

    # ------------------------------------------------------------------
    # Conversion and Display
    # ------------------------------------------------------------------

    def materialize(
        self,
        target_tz: TimezoneInput | None = None,
    ) -> datetime:
        """Return a timezone-aware datetime suitable for comparison or display.

        Args:
            target_tz (Optional[str]): Target timezone identifier.
                If None, defaults to the date's own timezone or UTC.

        Returns:
            Optional[datetime]: A timezone-aware datetime, or None if value is missing.
        """

        # Determine which timezone to use
        tz: TimezoneLike = parse_timezone(target_tz or self.timezone)

        if self.kind == DateKind.FLOATING:
            # Floating dates are naive, so we attach the chosen timezone
            return self.value.replace(tzinfo=tz)

        # Fixed dates are stored in UTC, so we convert to target timezone
        return self.value.astimezone(tz)

    def format(self, fmt: str = "%Y-%m-%d %H:%M") -> str | None:
        """Format the date into a string considering its nature.

        Args:
            fmt (str): Format string for datetime (default: "%Y-%m-%d %H:%M").

        Returns:
            str | None: Formatted string representation, or None if value is missing.
        """

        dt_aware: datetime = self.materialize(self.timezone)

        suffix: str = ""
        if self.kind == DateKind.FLOATING:
            suffix = " (Local)"

        return f"{dt_aware.strftime(fmt)}{suffix}"

    def __str__(self) -> str:
        """Default string representation of AxiomDate."""
        return str(self.format())


@dataclass(frozen=True)
class DueDate(AxiomDate):
    """
    Specialization of AxiomDate focused on deadlines and due dates.

    This class enforces stricter validation rules to ensure that
    due dates are realistic and consistent with business logic.
    """

    # ------------------------------------------------------------------
    # Business Logic
    # ------------------------------------------------------------------

    def _extra_validation(self) -> None:
        """Perform additional validation specific to due dates.

        Raises:
            ValidationException: If the due date is unrealistically old.
        """
        if self.value.year < 2000:
            raise ValidationException("Due date seems invalid (too old).")

    def is_overdue(self, now_reference: datetime) -> bool:
        """Check if the due date has expired.

        Args:
            now_reference (datetime): The "current time" to compare against.
                Must be timezone-aware (UTC or valid IANA timezone).

        Returns:
            bool: True if the due date has passed, False otherwise.

        Raises:
            ValidationException: If `now_reference` is
                naive or uses an unsupported timezone.
        """

        if now_reference.tzinfo is None:
            raise ValidationException("Reference 'now' must be timezone-aware")

        is_iana: bool = isinstance(now_reference.tzinfo, ZoneInfo)
        is_utc: bool = now_reference.tzinfo == UTC

        if not (is_iana or is_utc):
            raise ValidationException(
                "Reference 'now' must use an IANA timezone or UTC"
            )

        try:
            # A floating date is wall-clock time in its own zone (the user's
            # when it was set), never in the zone `now` happens to carry:
            # 23:59 in São Paulo is not 23:59 UTC. Fixed dates are instants.
            my_limit: datetime = self.materialize()
            return now_reference > my_limit

        except (ValueError, TypeError):
            # Safe fallback
            return False

    def remaining_time(self, now_reference: datetime) -> timedelta:
        """Return the remaining time until the due date.

        Args:
            now_reference (datetime): The "current time" to compare against.

        Returns:
            timedelta: Time remaining until the due date.
                Negative if overdue, 0 if value is missing.
        """

        target_date: datetime = self.materialize()
        return target_date - now_reference

    # ------------------------------------------------------------------
    # Specific Factories (Optional, but useful for readability)
    # ------------------------------------------------------------------

    @classmethod
    def as_deadline(cls, axiom_date: AxiomDate) -> "DueDate":
        """Convert a generic AxiomDate into a DueDate.

        Args:
            axiom_date (AxiomDate): The source date to convert.

        Returns:
            DueDate: A specialized due date instance with the same value,
            kind, and timezone as the original AxiomDate.
        """
        return cls(
            value=axiom_date.value,
            kind=axiom_date.kind,
            timezone=axiom_date.timezone,
        )


def parse_timezone(
    tz_input: TimezoneInput | None,
) -> TimezoneLike:
    """
    Parse and normalize diverse timezone formats into a valid Python tzinfo object.

    Supported formats:
        - None / Empty -> Defaults to UTC
        - ZoneInfo or timezone instances (returns as-is)
        - IANA Strings (e.g., "America/Sao_Paulo", "UTC")
        - Offset Strings (e.g., "UTC-03:00", "-03:00", "+0530", "Z")
    """

    if not tz_input:
        return UTC

    # 1. If it's already a valid tzinfo object, return it directly
    if isinstance(tz_input, (ZoneInfo, dt_timezone)):
        return tz_input

    # 2. If it's the abstract class tzinfo, safely extract tzname
    if isinstance(tz_input, tzinfo):
        tz_str = tz_input.tzname(None) or "UTC"
    # 3. Last, tz_input is a str
    else:
        tz_str = tz_input.strip()

    # 4. Handle literal "Z" or "UTC"
    if tz_str.upper() in ("Z", "UTC"):
        return UTC

    # 5. Handle Offset Strings (e.g., "UTC-03:00", "-03:00", "+05:30", "+0530")
    # Regex captures:
    # -- optional 'UTC',
    # -- sign (+/-),
    # -- hours (2 digits),
    # -- optional separator (:),
    # -- minutes (2 digits)
    offset_pattern: re.Pattern[str] = re.compile(
        r"^(?:UTC)?([+-])(\d{2}):?(\d{2})?$",
        re.IGNORECASE,
    )

    if match := offset_pattern.match(tz_str):
        sign, hours, minutes = match.groups()
        total_minutes: int = int(hours) * 60 + int(minutes or 0)
        if sign == "-":
            total_minutes = -total_minutes
        return dt_timezone(timedelta(minutes=total_minutes))

    # 6. Handle IANA Timezone Strings (e.g., "America/Sao_Paulo")
    try:
        return ZoneInfo(tz_str)
    except ZoneInfoNotFoundError:
        # Fallback
        return UTC


def build_axiom_date(
    dt: datetime,
    *,
    is_floating: bool,
    tz: TimezoneInput | None = None,
) -> AxiomDate:
    """Factory function to build an AxiomDate instance.

    Args:
        dt (Optional[datetime]): The base datetime. If None, `fallback_now` is used.
        is_floating (bool): Whether the date should
            be treated as floating (local clock time).
        tz (TimezoneInput): IANA timezone identifier. Required for floating dates.

    Returns:
        AxiomDate: A properly constructed AxiomDate (fixed or floating).

    Raises:
        ValidationException: If floating dates are provided without a timezone.
    """

    base: datetime = dt
    resolved_tz: TimezoneLike = parse_timezone(tz)

    if is_floating:
        # Floating dates must be naive (no tzinfo)
        if base.tzinfo is not None:
            base = base.replace(tzinfo=None)

        if not tz:
            raise ValidationException("Floating dates require a timezone.")

        if isinstance(resolved_tz, ZoneInfo):
            tz_name: str = resolved_tz.key
        else:
            tz_name = resolved_tz.tzname(None) or "UTC"

        return AxiomDate.floating(base, tz_name)

    # FIXED case
    if base.tzinfo is None:
        base = base.replace(tzinfo=resolved_tz)

    return AxiomDate.fixed(base)
