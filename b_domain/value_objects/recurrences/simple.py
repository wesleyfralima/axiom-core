import calendar
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from b_domain.value_objects.enums import RecurrenceInterval
from b_domain.value_objects.recurrences import RecurrenceRule


def add_months(source_date: datetime, months: int, target_day: Optional[int] = None) -> datetime:
    """Add months to a given date, handling end-of-month overflows.

    Args:
        source_date (datetime): The original date to adjust.
        months (int): Number of months to add.
        target_day (Optional[int], optional): Preferred day of the month to anchor.
            If None, defaults to the day of `source_date`.

    Returns:
        datetime: The adjusted date, clamped to the last valid day of the target month if necessary.

    Example:
        >>> add_months(datetime(2026, 1, 31), 1)
        datetime(2026, 2, 28)
    """
    month: int = source_date.month - 1 + months
    year: int = source_date.year + month // 12
    month: int = month % 12 + 1

    days_in_new_month: int = calendar.monthrange(year, month)[1]
    original_day_preference: int = target_day if target_day else source_date.day
    day: int = min(original_day_preference, days_in_new_month)

    return source_date.replace(year=year, month=month, day=day)


@dataclass(frozen=True, kw_only=True)
class SimpleIntervalRule(RecurrenceRule):
    """Rule for continuous, simple interval-based recurrences.

    Handles straightforward repetitions like "every 3 days", "every 2 weeks",
    or "every month on the exact same numerical day".

    Attributes:
        frequency (RecurrenceInterval): The unit of the interval (HOURLY, DAILY, WEEKLY, MONTHLY, YEARLY).
    """

    frequency: RecurrenceInterval

    def __post_init__(self):
        """Initialize frequency mapping for RRULE string."""
        super().__post_init__()

        freq_map = {
            RecurrenceInterval.HOURLY: "HOURLY",
            RecurrenceInterval.DAILY: "DAILY",
            RecurrenceInterval.WEEKLY: "WEEKLY",
            RecurrenceInterval.MONTHLY: "MONTHLY",
            RecurrenceInterval.YEARLY: "YEARLY",
        }

        object.__setattr__(self, "_freq", freq_map[self.frequency])

    def get_first_valid_occurrence(self) -> datetime:
        """
        For simple intervals, the first occurrence is the start_date itself.
        Unlike complex weekly or monthly rules, there are no filters that
        could push the first date forward.
        """
        return self.start_date.materialize()

    def get_next_occurrence(self, last_occurrence: Optional[datetime] = None) -> Optional[datetime]:
        """Calculate the exact next occurrence by adding the interval unit.

        Args:
            last_occurrence (Optional[datetime], optional): The last occurrence
                to continue from. Defaults to None.

        Returns:
            Optional[datetime]: The next valid occurrence if available,
            otherwise None.
        """

        # 1. Base case: First occurrence
        if last_occurrence is None:
            first = self.get_first_valid_occurrence()
            if self._is_exhausted(first):
                return None
            return first.replace(microsecond=0)

        # 2. Normalize timezone
        last = self._normalize_comparison_date(last_occurrence)

        # 3. Apply the specific mathematical interval
        candidate = self._add_interval(last)

        # 4. Check global limits (end_date or count)
        if self._is_exhausted(candidate):
            return None

        return candidate.replace(microsecond=0)

    def _add_interval(self, current: datetime) -> datetime:
        """Execute the specific timedelta math based on the frequency type.

        Args:
            current (datetime): The current occurrence.

        Returns:
            datetime: The next occurrence after applying the interval.
        """

        base_dt: datetime = self.start_date.materialize()

        if self.frequency == RecurrenceInterval.HOURLY:
            dt = current + timedelta(hours=self.interval)

        elif self.frequency == RecurrenceInterval.DAILY:
            dt = current + timedelta(days=self.interval)

        elif self.frequency == RecurrenceInterval.WEEKLY:
            dt = current + timedelta(weeks=self.interval)

        elif self.frequency == RecurrenceInterval.MONTHLY:
            # Preserve the original day of start_date as anchor to avoid date degradation
            # (e.g., Jan 31 -> Feb 28 -> back to 31 in March).
            dt = add_months(current, self.interval, target_day=base_dt.day)

        elif self.frequency == RecurrenceInterval.YEARLY:
            dt = add_months(current, self.interval * 12, target_day=base_dt.day)

        else:
            dt = current

        # Ensure the original time and timezone (naive/aware) remain unchanged
        return self._combine_with_start_time(dt.date())
