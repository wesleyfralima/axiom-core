from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Set

from b_domain.exceptions import InvalidWeekDayValue
from b_domain.value_objects.recurrences import RecurrenceRule


@dataclass(frozen=True, kw_only=True)
class WeeklyByDaysRule(RecurrenceRule):
    """Rule for occurrences on specific days of the week.

    Handles recurrences like "Every Tuesday and Thursday" or
    "Every 2 weeks on Mondays".

    Attributes:
        days_of_week (Set[int]): Weekdays to repeat on (0=Monday, 6=Sunday).
    """

    days_of_week: Set[int]

    def __post_init__(self) -> None:
        """Validate the specific invariants for weekly rules.

        Raises:
            InvalidWeekDayValue: If `days_of_week` is empty or contains invalid values.
        """

        super().__post_init__()
        object.__setattr__(self, "_freq", "WEEKLY")

        if not self.days_of_week:
            raise InvalidWeekDayValue("days_of_week cannot be empty.")

        invalids: list[int] = [d for d in self.days_of_week if not (0 <= d <= 6)]
        if invalids:
            raise InvalidWeekDayValue(str(invalids))

    def _rrule_extra_parts(self) -> list[str]:
        """Generate BYDAY part for RFC 5545 RRULE string."""
        day_map = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
        days_str = ",".join(day_map[d] for d in sorted(self.days_of_week))
        return [f"BYDAY={days_str}"]

    def get_first_valid_occurrence(self) -> datetime:
        """
        Calculate the first valid occurrence.
        It may be the start_date itself or the next allowed weekday.
        """

        base_dt: datetime = self.start_date.materialize()

        # 1. Normalize start_date for comparison logic
        start_norm = self.normalize_comparison_date(base_dt)

        # 2. Find the start of the week (Monday) for start_date
        week_start = start_norm - timedelta(days=start_norm.weekday())

        # 3. Search for the first allowed weekday >= start_date
        valid_days = sorted(self.days_of_week)
        for day_idx in valid_days:
            candidate_date = (week_start + timedelta(days=day_idx)).date()
            candidate = self._combine_with_start_time(candidate_date)

            if candidate >= start_norm:
                return candidate

        # 4. If start_date is after all selected days in that week,
        # advance to the next valid week based on interval
        next_week_start = week_start + timedelta(weeks=self.interval)
        candidate_date = (next_week_start + timedelta(days=valid_days[0])).date()
        return self._combine_with_start_time(candidate_date)

    def get_next_occurrence(self, last_occurrence: Optional[datetime] = None) -> Optional[datetime]:
        """Calculate the next occurrence considering the specified weekdays."""

        base_dt: datetime = self.start_date.materialize()

        # 1. Base case: First occurrence
        if last_occurrence is None:
            first = self.get_first_valid_occurrence()
            if self._is_exhausted(first):
                return None
            return first

        # 2. Normalize timezone for math
        last = self.normalize_comparison_date(last_occurrence)
        valid_days = sorted(self.days_of_week)

        # 3. Find week boundaries (Monday as start of week)
        last_week_start = last - timedelta(days=last.weekday())

        # Normalize start_date to find anchor week
        start_norm = self.normalize_comparison_date(base_dt)
        start_week_start = start_norm - timedelta(days=start_norm.weekday())

        # 4. Calculate how many full weeks have passed since anchor week
        weeks_diff = (last_week_start.date() - start_week_start.date()).days // 7

        # 5. Try to find a valid day later in the CURRENT week
        if weeks_diff % self.interval == 0:
            for day_idx in valid_days:
                candidate_date = (last_week_start + timedelta(days=day_idx)).date()
                candidate = self._combine_with_start_time(candidate_date)

                if candidate > last:
                    if self._is_exhausted(candidate):
                        return None
                    return candidate

        # 6. Advance to the NEXT valid week based on interval
        remainder = weeks_diff % self.interval
        weeks_to_advance = self.interval - remainder
        next_week_start = last_week_start + timedelta(weeks=weeks_to_advance)

        # Return the first valid day of that new week
        candidate_date = (next_week_start + timedelta(days=valid_days[0])).date()
        candidate = self._combine_with_start_time(candidate_date)

        if self._is_exhausted(candidate):
            return None

        return candidate
