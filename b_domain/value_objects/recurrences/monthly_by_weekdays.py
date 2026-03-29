import calendar
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional, Set

from b_domain.exceptions.recurrence import InvalidWeekDayValue
from b_domain.value_objects.recurrences import RecurrenceRule


@dataclass(frozen=True, kw_only=True)
class MonthlyAllWeekdaysRule(RecurrenceRule):
    """Rule for occurrences on all specific weekdays within a month.

    Handles recurrences like "Every Friday of the month" or
    "Every Tuesday and Thursday, every 2 months".

    Attributes:
        days_of_week (Set[int]): Weekdays to repeat on (0=Monday, 6=Sunday).
    """

    days_of_week: Set[int]

    def __post_init__(self) -> None:
        """Validate the specific invariants for weekdays.

        Raises:
            InvalidWeekDayValue: If `days_of_week` is empty or contains
            values outside the valid range (0–6).
        """

        super().__post_init__()
        object.__setattr__(self, "_freq", "MONTHLY")

        if not self.days_of_week:
            raise InvalidWeekDayValue("days_of_week cannot be empty.")

        # Ensure all weekdays are within 0–6 (Monday–Sunday)
        if any(d < 0 or d > 6 for d in self.days_of_week):
            raise InvalidWeekDayValue(f"Invalid weekdays: {self.days_of_week}. Must be 0-6.")

    def _rrule_extra_parts(self) -> list[str]:
        """Generate BYDAY part for RFC 5545 RRULE string.

        This method maps the numeric weekdays (0=Monday, 6=Sunday) into
        RFC 5545 weekday abbreviations (MO, TU, WE, TH, FR, SA, SU).
        It then builds the BYDAY clause including all selected weekdays.

        Returns:
            list[str]: A list containing the BYDAY clause with the chosen weekdays.
        """

        # Mapping from numeric weekdays (0–6) to RFC 5545 abbreviations
        day_map: list[str] = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]

        # Build the BYDAY string with all selected weekdays
        days_str: str = ",".join(
            day_map[d]
            for d in sorted(self.days_of_week)
        )

        return [f"BYDAY={days_str}"]

    def get_first_valid_occurrence(self) -> datetime:
        """
        Locate the first occurrence (allowed weekday)
        equal to or later than start_date within the valid month.
        """

        base_dt: datetime = self.start_date.materialize()
        start_norm = self._normalize_comparison_date(base_dt)

        scan_year = start_norm.year
        scan_month = start_norm.month

        # Search horizon of 120 months
        for _ in range(120):
            last_day_of_month = calendar.monthrange(scan_year, scan_month)[1]

            # Iterate through all days of the current month
            for day_num in range(1, last_day_of_month + 1):
                d = date(scan_year, scan_month, day_num)

                # If the weekday is one of the allowed ones
                if d.weekday() in self.days_of_week:
                    candidate = self._combine_with_start_time(d)

                    # The first occurrence must be greater than or equal to start_date
                    if candidate >= start_norm:
                        return candidate

            # If no valid day exists in the current month (or all have passed),
            # advance according to the interval (Anchor Date logic)
            months_since_start = (scan_year - base_dt.year) * 12 + (scan_month - base_dt.month)
            months_to_advance = self.interval - (months_since_start % self.interval)

            total_months = scan_month - 1 + months_to_advance
            scan_year = scan_year + (total_months // 12)
            scan_month = (total_months % 12) + 1

        return base_dt  # Safety fallback

    def get_next_occurrence(self, last_occurrence: Optional[datetime] = None) -> Optional[datetime]:
        """Calculate the next occurrence by iterating through the month's days.

        If no `last_occurrence` is provided, the first valid occurrence is returned.
        Otherwise, the method scans month by month (up to 120 months ahead) to
        find the next valid weekday occurrence based on the allowed weekdays.

        Args:
            last_occurrence (Optional[datetime], optional): The last occurrence
                to continue from. Defaults to None.

        Returns:
            Optional[datetime]: The next valid occurrence if available,
            otherwise None.
        """

        base_dt: datetime = self.start_date.materialize() if self.end_date else None

        if last_occurrence is None:
            first = self.get_first_valid_occurrence()
            return first if not self._is_exhausted(first) else None

        last = self._normalize_comparison_date(last_occurrence)

        scan_year = last.year
        scan_month = last.month

        # Safety limit (120 months) to prevent infinite loops
        for _ in range(120):
            last_day_of_month = calendar.monthrange(scan_year, scan_month)[1]

            # 1. Iterate through all valid days of the current scanning month
            for day_num in range(1, last_day_of_month + 1):
                d = date(scan_year, scan_month, day_num)

                # Check if the day matches one of the required weekdays
                if d.weekday() in self.days_of_week:
                    candidate = self._combine_with_start_time(d)

                    # Ensure candidate is strictly in the future
                    if candidate > last:
                        if self._is_exhausted(candidate):
                            return None
                        return candidate

            # 2. Advance to the next valid month based on the interval
            months_diff = (scan_year - base_dt.year) * 12 + (scan_month - base_dt.month)
            remainder = months_diff % self.interval
            months_to_advance = self.interval - remainder

            new_month = scan_month - 1 + months_to_advance
            scan_year = scan_year + (new_month // 12)
            scan_month = (new_month % 12) + 1

        return None
