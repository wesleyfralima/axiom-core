from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime

from a_core import ValidationException, ValueObject
from a_core.text import join_naturally
from b_domain.exceptions.recurrence import (
    EndDateBeforeStartDate,
    InvalidIntervalValue,
    MutuallyExclusiveEndDateAndCount,
)
from b_domain.value_objects.dates import AxiomDate

WEEKDAY_NAMES: tuple[str, ...] = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


@dataclass(frozen=True, kw_only=True)
class RecurrenceRule(ValueObject, ABC):
    """Base contract for all recurrence strategies.

    This class enforces global recurrence invariants and provides
    shared utilities for timezone normalization, end condition checking,
    and bulk occurrence generation.

    Attributes:
        start_date (AxiomDate): The date and time when repetition starts.
        interval (int): The repetition interval. Defaults to 1.
        end_date (Optional[AxiomDate]): The date and time when repetition ends.
        count (Optional[int]): Maximum number of repetitions.
        _freq (str): Internal frequency marker (set by subclasses).
    """

    start_date: AxiomDate
    interval: int = 1
    end_date: AxiomDate | None = None
    count: int | None = None

    _freq: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Validate universal recurrence invariants.

        Raises:
            InvalidIntervalValue: If interval is less than 1.
            MutuallyExclusiveEndDateAndCount: If both end_date and count are set.
            ValidationException: If start_date and end_date have different kinds.
            EndDateBeforeStartDate: If end_date is before or equal to start_date.
        """

        if self.interval < 1:
            raise InvalidIntervalValue("Interval must be at least 1.")

        if self.end_date:
            # end_date and count cannot coexist
            if self.count:
                raise MutuallyExclusiveEndDateAndCount()

            if self.start_date.kind != self.end_date.kind:
                raise ValidationException(
                    "start_date and end_date must share "
                    "the same DateKind (floating/fixed)."
                )

            # start and end dates must be logically coherent
            dt_start: datetime = self.start_date.materialize()
            dt_end: datetime = self.end_date.materialize()
            if dt_end <= dt_start:
                raise EndDateBeforeStartDate(
                    start_date=dt_start,
                    end_date=dt_end,
                )

    # noinspection PyMethodMayBeStatic
    def supports_native_sync(self) -> bool:
        """
        Indica se esta regra pode ser exportada como uma RRULE padrão
        para calendários externos (Google, Outlook, etc).

        Por padrão, assumimos True. Regras customizadas devem sobrescrever.
        """
        return True

    # --------------------------------------------------------------------------
    # ABSTRACT CONTRACTS (Must be implemented by subclasses)
    # --------------------------------------------------------------------------

    @abstractmethod
    def get_next_occurrence(
        self, last_occurrence: datetime | None = None
    ) -> datetime | None:
        """Calculates the exact next occurrence based on the specific rule strategy.

        Args:
            last_occurrence (Optional[datetime]): The last valid occurrence.

        Returns:
            Optional[datetime]: The next valid occurrence, or None if exhausted.
        """

    @abstractmethod
    def get_first_valid_occurrence(self) -> datetime:
        """
        Calcula a primeira data válida para esta recorrência,
        igual ou após a start_date.
        """

    @abstractmethod
    def describe_pattern(self) -> str:
        """Describe, in English, when the rule repeats — without its end.

        End conditions (``count``/``end_date``) are left to the caller, who
        decides how to phrase them.

        Returns:
            str: A phrase such as "Every 2 weeks on Mondays and Fridays".
        """

    @property
    def rrule_string(self) -> str:
        """Generate the RFC 5545 recurrence rule string.

        This property builds the recurrence rule string (`RRULE`) according
        to the iCalendar specification (RFC 5545). It includes frequency,
        interval, end conditions (count or until), and any additional parts
        defined by subclasses.

        Returns:
            str: A fully formatted recurrence rule string, e.g.,
            "RRULE:FREQ=DAILY;INTERVAL=2;COUNT=10".
        """
        parts: list = [f"FREQ={self._freq}"]

        if self.interval > 1:
            parts.append(f"INTERVAL={self.interval}")

        if self.count:
            parts.append(f"COUNT={self.count}")
        else:
            until: str | None = self._format_until()
            if until:
                parts.append(f"UNTIL={until}")

        # Extension from children
        parts.extend(self._rrule_extra_parts())

        return f"RRULE:{';'.join(parts)}"

    # --------------------------------------------------------------------------
    # SHARED ENGINE LOGIC
    # --------------------------------------------------------------------------

    def get_next_n_occurrences(
        self, n: int = 5, start_from: datetime | None = None
    ) -> list[datetime]:
        """Return the next `n` occurrences of the recurrence rule.

        This acts as a generic engine that relies on the subclass's
        `get_next_occurrence` implementation.
        """

        occurrences: list[datetime] = []
        first_valid: datetime | None = None
        last: datetime | None

        if start_from is not None:
            first_valid = self._get_closest_occurrence(start_from, before=False)
            if first_valid:
                occurrences.append(first_valid)
                n -= 1

        last = first_valid

        for _ in range(n):
            next_occurrence = self.get_next_occurrence(last)

            if not next_occurrence:
                break

            occurrences.append(next_occurrence)
            last = next_occurrence

            # Limit the generated batch size to self.count
            if self.count and len(occurrences) >= self.count:
                break

        return occurrences

    def _get_closest_occurrence(
        self, reference: datetime, before: bool = False
    ) -> datetime | None:
        """Find the closest occurrence relative to a reference datetime."""

        if reference:
            reference = self.normalize_comparison_date(reference)

        candidate: datetime | None
        last_candidate: datetime | None = None

        for _ in range(10_000):  # Safety limit
            candidate = self.get_next_occurrence(last_candidate)
            if candidate is None:
                break

            if not self._check_end_conditions(candidate):
                break

            if candidate >= reference:
                return last_candidate if before else candidate

            last_candidate = candidate

        return last_candidate if before else None

    def _format_until(self) -> str | None:
        """Format ``end_date`` for use in rrule_string.

        Converts the `end_date` into the proper RFC 5545 `UNTIL` format.
        If the date is floating (no timezone), it is formatted without a
        trailing `Z`. If the date is fixed, it is normalized to UTC and
        formatted with a `Z` suffix.

        Returns:
            Optional[str]: A formatted `UNTIL` string if `end_date` is set,
            otherwise None.
        """

        if not self.end_date:
            return None

        if self.end_date.is_floating:
            return self.end_date.value.strftime("%Y%m%dT%H%M%S")

        return self.end_date.materialize("UTC").strftime("%Y%m%dT%H%M%SZ")

    # noinspection PyMethodMayBeStatic
    def _rrule_extra_parts(self) -> list[str]:
        """Define extra parts for ``rrule_string``.

        Subclasses can override this method to add custom recurrence
        components (e.g., BYDAY, BYMONTHDAY) to the rule string.

        Returns:
            list[str]: A list of additional RFC 5545 rule parts.
        """
        return []

    # --------------------------------------------------------------------------
    # UTILITIES FOR SUBCLASSES
    # --------------------------------------------------------------------------

    def _every(self, unit: str) -> str:
        """Open a description with the interval: "Every day", "Every 3 days"."""

        if self.interval == 1:
            return f"Every {unit}"
        return f"Every {self.interval} {unit}s"

    @staticmethod
    def _weekdays(days: set[int], plural: bool = False) -> str:
        """Name weekdays in order: "Monday and Friday" or "Mondays and Fridays"."""

        suffix: str = "s" if plural else ""
        return join_naturally(f"{WEEKDAY_NAMES[d]}{suffix}" for d in sorted(days))

    def normalize_comparison_date(self, dt: datetime) -> datetime:
        """Normalize a datetime for comparison with recurrence rules.

        Ensures consistent comparison between floating (naive) and fixed
        (timezone-aware) datetimes. If the rule is floating and the candidate
        datetime is timezone-aware, the timezone is stripped. If the rule is
        fixed and the candidate datetime is naive, the rule's timezone is applied.

        Args:
            dt (datetime): The candidate datetime to normalize.

        Returns:
            datetime: A normalized datetime suitable for comparison.
        """

        rule_dt: datetime = self.start_date.materialize()
        is_rule_naive: bool = self.start_date.is_floating is None
        is_dt_naive: bool = dt.tzinfo is None

        if is_rule_naive and not is_dt_naive:
            return dt.replace(tzinfo=None)

        if not is_rule_naive and is_dt_naive:
            return dt.replace(tzinfo=rule_dt.tzinfo)

        return dt

    def _combine_with_start_time(self, d: date) -> datetime:
        """Combine a date with the recurrence rule's start time safely.

        Uses the time component of the rule's `start_date` and merges it
        with the provided date. Preserves timezone information if present.

        Args:
            d (date): The date to combine with the rule's start time.

        Returns:
            datetime: A datetime combining the given date and the rule's start time.
        """
        base_dt: datetime = self.start_date.materialize()
        dt: datetime = datetime.combine(d, base_dt.time())

        if base_dt.tzinfo:
            dt = dt.replace(tzinfo=base_dt.tzinfo)

        return dt.replace(microsecond=0)

    def _check_end_conditions(self, dt: datetime) -> bool:
        """Check if the given date respects recurrence end conditions.

        Validates whether the candidate datetime falls before or on the
        recurrence `end_date`. Normalization ensures floating rules are
        compared consistently.

        Args:
            dt (datetime): The candidate datetime to check.

        Returns:
            bool: True if the candidate respects end conditions, False otherwise.
        """
        if self.end_date:
            limit: datetime = self.end_date.materialize()

            # Normalize candidate and limit for consistent comparison
            normalized_dt: datetime = self.normalize_comparison_date(dt)
            normalized_limit: datetime = self.normalize_comparison_date(limit)

            if normalized_dt > normalized_limit:
                return False

        return True

    def _is_exhausted(self, next_date: datetime, current_count: int = 0) -> bool:
        """Helper for subclasses to check if the recurrence has reached its limits."""

        if not self._check_end_conditions(next_date):
            return True
        if self.count and current_count >= self.count:
            return True
        return False
