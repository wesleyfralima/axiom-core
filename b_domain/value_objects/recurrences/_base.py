from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Optional

from a_core import ValidationException
from a_core.base import ValueObject
from b_domain.exceptions.recurrence import (
    EndDateBeforeStartDate,
    InvalidIntervalValue,
    MutuallyExclusiveEndDateAndCount,
)


@dataclass(frozen=True, kw_only=True)
class RecurrenceRule(ValueObject, ABC):
    """Base contract for all recurrence strategies.

    This class enforces global recurrence invariants and provides
    shared utilities for timezone normalization, end condition checking,
    and bulk occurrence generation.

    Attributes:
        start_date (datetime): The date and time when repetition starts.
        interval (int): The repetition interval. Defaults to 1.
        end_date (Optional[datetime]): The date and time when repetition ends.
        count (Optional[int]): Maximum number of repetitions.
    """

    start_date: datetime
    interval: int = 1
    end_date: Optional[datetime] = None
    count: Optional[int] = None

    def __post_init__(self) -> None:
        """Validate universal recurrence invariants."""

        if self.interval < 1:
            raise InvalidIntervalValue("Interval must be at least 1.")

        if self.end_date:
            # end_date and count cannot coexist
            if self.count:
                raise MutuallyExclusiveEndDateAndCount()

            # start_date and end_date must share the same timezone type
            if self.start_date.tzinfo is None and self.end_date.tzinfo is not None:
                raise ValidationException(
                    "If start_date is naive (floating), end_date must also be naive."
                )
            if self.start_date.tzinfo is not None and self.end_date.tzinfo is None:
                raise ValidationException(
                    "If start_date is aware (fixed), end_date must also be aware."
                )

            # end_date must be strictly after start_date
            if self.end_date <= self.start_date:
                raise EndDateBeforeStartDate(start_date=self.start_date, end_date=self.end_date)

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
    def get_next_occurrence(self, last_occurrence: Optional[datetime] = None) -> Optional[datetime]:
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

    @property
    @abstractmethod
    def rrule_string(self) -> str:
        """Returns the specific RFC 5545 string for this rule."""

    # --------------------------------------------------------------------------
    # SHARED ENGINE LOGIC
    # --------------------------------------------------------------------------

    def get_next_n_occurrences(self, n: int = 5, start_from: Optional[datetime] = None) -> List[datetime]:
        """Return the next `n` occurrences of the recurrence rule.

        This acts as a generic engine that relies on the subclass's
        `get_next_occurrence` implementation.
        """

        occurrences: List[datetime] = []
        first_valid: Optional[datetime] = None

        if start_from is not None:
            first_valid = self._get_closest_occurrence(start_from, before=False)
            if first_valid:
                occurrences.append(first_valid)
                n = n - 1

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

    def _get_closest_occurrence(self, reference: datetime, before: bool = False) -> Optional[datetime]:
        """Find the closest occurrence relative to a reference datetime."""

        if reference:
            reference = self._normalize_comparison_date(reference)

        candidate: Optional[datetime]
        last_candidate: Optional[datetime] = None

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

    # --------------------------------------------------------------------------
    # UTILITIES FOR SUBCLASSES
    # --------------------------------------------------------------------------

    def _normalize_comparison_date(self, dt: datetime) -> datetime:
        """Normalize a datetime for comparison with recurrence rules."""

        is_rule_naive: bool = self.start_date.tzinfo is None
        is_dt_naive: bool = dt.tzinfo is None

        if is_rule_naive and not is_dt_naive:
            return dt.replace(tzinfo=None)

        if not is_rule_naive and is_dt_naive:
            return dt.replace(tzinfo=self.start_date.tzinfo)

        return dt

    def _combine_with_start_time(self, d: date) -> datetime:
        """Combine a date with the recurrence rule's start time safely."""
        dt: datetime = datetime.combine(d, self.start_date.time())

        if self.start_date.tzinfo:
            dt = dt.replace(tzinfo=self.start_date.tzinfo)

        return dt.replace(microsecond=0)

    def _check_end_conditions(self, dt: datetime) -> bool:
        """Check if the given date respects end conditions (end_date)."""
        if self.end_date and dt > self.end_date:
            return False
        return True

    def _is_exhausted(self, next_date: datetime, current_count: int = 0) -> bool:
        """Helper for subclasses to check if the recurrence has reached its limits."""

        if not self._check_end_conditions(next_date):
            return True
        if self.count and current_count >= self.count:
            return True
        return False
