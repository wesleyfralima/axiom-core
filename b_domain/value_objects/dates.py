from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from a_core.exceptions import ValidationException


class DateKind(StrEnum):
    """
    Define the semantic nature of a date.

    Attributes:
        FIXED: An absolute instant in time (e.g., "Global Meeting at 14:00 UTC").
        FLOATING: A local clock time, independent of timezone (e.g., "Wake up at 07:00 AM").
    """
    FIXED = "fixed"         # An absolute instant (e.g., Global Meeting at 14:00 UTC)
    FLOATING = "floating"   # A local clock time (e.g., Wake up at 07:00 AM)


@dataclass(frozen=True, order=True)
class AxiomDate:
    """
    Universal temporal primitive for the Axiom application.
    Replaces raw `datetime` usage to ensure consistent timezone handling.

    Attributes:
        value (datetime | None): The underlying datetime value.
            - If FIXED: must be timezone-aware (preferably UTC).
            - If FLOATING: must be naive.
        kind (DateKind): Defines whether the date is FIXED or FLOATING.
        timezone (Optional[str]): The IANA timezone identifier (e.g., "America/Sao_Paulo").
            - For FLOATING: required, used as the anchor to interpret the local time
              and handle Daylight Saving Time (DST).
            - For FIXED: optional, used as preferred display timezone.
    """

    # Value is used for ordering (sorting). Must be consistent with kind.
    value: datetime | None

    kind: DateKind = field(compare=False)

    # Timezone anchor or preferred display zone
    timezone: Optional[str] = field(default=None, compare=False)
    """
    The IANA timezone identifier (e.g., "America/Sao_Paulo") 
    used as the anchor to interpret floating dates and handle 
    Daylight Saving Time (DST) changes accurately.
    """

    def __post_init__(self):
        """Ensure data integrity upon creation."""

        if self.value is None:
            return

        # Validation for Floating dates
        if self.kind == DateKind.FLOATING:
            if self.value.tzinfo is not None:
                raise ValidationException("Floating dates must store a naive datetime.")
            if not self.timezone:
                raise ValidationException("Floating dates require a valid timezone name.")
            try:
                ZoneInfo(self.timezone)
            except ZoneInfoNotFoundError:
                raise ValidationException("Invalid timezone for floating date")

        # Validation for Fixed dates
        elif self.kind == DateKind.FIXED:
            if self.value.tzinfo is None:
                raise ValidationException("Fixed dates must store a timezone-aware datetime.")
            # Normalize to UTC for consistency
            object.__setattr__(self, "value", self.value.astimezone(timezone.utc))

        self._extra_validation()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extra_validation(self):
        """Hook for subclasses performing extra validation."""

    # ------------------------------------------------------------------
    # Factories (Static Constructors)
    # ------------------------------------------------------------------

    @classmethod
    def empty(cls, kind: DateKind | None = DateKind.FLOATING) -> "AxiomDate":
        """Create an empty AxiomDate with no value."""
        return cls(value=None, kind=kind, timezone=None)

    @classmethod
    def fixed(cls, dt: datetime) -> "AxiomDate":
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
    def floating(cls, dt: datetime, source_tz: str) -> "AxiomDate":
        """Create a floating AxiomDate.

        Args:
            dt (datetime): Naive datetime representing the floating time.
            source_tz (str): IANA timezone identifier (e.g., "America/Sao_Paulo").

        Returns:
            AxiomDate: A floating date instance anchored to the given timezone.

        Raises:
            ValidationException: If the datetime is timezone-aware or the timezone is invalid.
        """
        return cls(
            value=dt,
            kind=DateKind.FLOATING,
            timezone=source_tz,
        )

    @classmethod
    def now(cls) -> "AxiomDate":
        """Convenient factory to create 'now' as a fixed date in UTC."""
        return cls.fixed(datetime.now(timezone.utc))

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

    def materialize(self, target_tz: Optional[str] = None) -> Optional[datetime]:
        """Return a timezone-aware datetime suitable for comparison or display.

        Args:
            target_tz (Optional[str]): Target timezone identifier.
                If None, defaults to the date's own timezone or UTC.

        Returns:
            Optional[datetime]: A timezone-aware datetime, or None if value is missing.
        """

        if self.value is None:
            return None

        # Determine which timezone to use
        effective_tz_name: str = target_tz or self.timezone or "UTC"
        try:
            tz: ZoneInfo | timezone = ZoneInfo(effective_tz_name)
        except ZoneInfoNotFoundError:
            tz = ZoneInfo("UTC")

        if self.kind == DateKind.FLOATING:
            # Floating dates are naive, so we attach the chosen timezone
            return self.value.replace(tzinfo=tz)

        if self.kind == DateKind.FIXED:
            # Fixed dates are stored in UTC, so we convert to target timezone
            return self.value.astimezone(tz)

        return None

    def format(self, fmt: str = "%Y-%m-%d %H:%M") -> str | None:
        """Format the date into a string considering its nature.

        Args:
            fmt (str): Format string for datetime (default: "%Y-%m-%d %H:%M").

        Returns:
            str | None: Formatted string representation, or None if value is missing.
        """

        if self.value is None:
            return None

        dt_aware: datetime = self.materialize(self.timezone)

        suffix: str = ""
        if self.kind == DateKind.FLOATING:
            suffix = " (Local)"

        return f"{dt_aware.strftime(fmt)}{suffix}"

    def __str__(self) -> str:
        """Default string representation of AxiomDate."""
        return self.format()

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

    def _extra_validation(self):
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
            ValidationException: If `now_reference` is naive or uses an unsupported timezone.
        """

        if self.value is None:
            return False

        if now_reference.tzinfo is None:
            raise ValidationException("Reference 'now' must be timezone-aware")

        is_iana: bool = isinstance(now_reference.tzinfo, ZoneInfo)
        is_utc: bool = now_reference.tzinfo == timezone.utc
        if not (is_iana or is_utc):
            raise ValidationException("Reference 'now' must use an IANA timezone or UTC")

        try:
            # Materialize the due date into a timezone-aware datetime
            my_limit = self.materialize()
            # Compare consistently (same timezone context)
            return now_reference > my_limit
        except (ValueError, TypeError):
            # Safe fallback
            return False

    def remaining_time(self, now_reference: datetime) -> Optional[timedelta]:
        """Return the remaining time until the due date.

        Args:
            now_reference (datetime): The "current time" to compare against.

        Returns:
            Optional[timedelta]: Time remaining until the due date.
                Negative if overdue, None if value is missing.
        """

        if self.value is None:
            return None

        target_date = self.materialize()
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
            timezone=axiom_date.timezone
        )


def build_axiom_date(
    dt: Optional[datetime],
    *,
    is_floating: bool,
    tz: Optional[str],
    fallback_now: datetime
) -> AxiomDate:
    """Factory function to build an AxiomDate instance.

    Args:
        dt (Optional[datetime]): The base datetime. If None, `fallback_now` is used.
        is_floating (bool): Whether the date should be treated as floating (local clock time).
        tz (Optional[str]): IANA timezone identifier. Required for floating dates.
        fallback_now (datetime): Fallback datetime if `dt` is None.

    Returns:
        AxiomDate: A properly constructed AxiomDate (fixed or floating).

    Raises:
        ValidationException: If floating dates are provided without a timezone.
    """

    base = dt or fallback_now

    if is_floating:
        # Floating dates must be naive (no tzinfo)
        if base.tzinfo is not None:
            base = base.replace(tzinfo=None)

        if not tz:
            raise ValidationException("Floating dates require a timezone.")

        return AxiomDate.floating(base, tz)

    # FIXED case
    if base.tzinfo is None:
        # Policy decision: attach UTC or provided ZoneInfo
        if tz:
            base = base.replace(tzinfo=ZoneInfo(tz))
        else:
            base = base.replace(tzinfo=timezone.utc)

    return AxiomDate.fixed(base)
