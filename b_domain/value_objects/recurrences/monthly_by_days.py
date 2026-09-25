import calendar
from dataclasses import dataclass
from datetime import date, datetime

from a_core.text import join_naturally
from b_domain.exceptions.recurrence import InvalidMonthDayValue
from b_domain.value_objects.recurrences import RecurrenceRule


@dataclass(frozen=True, kw_only=True)
class MonthlyByDaysRule(RecurrenceRule):
    """Rule for occurrences on specific numeric days of the month.

    Handles recurrences like "Every 10th and 20th of the month".
    If a specified day exceeds the number of days in a given month
    (e.g., day 31 in February), that specific day is safely ignored
    for that month.

    Attributes:
        days_of_month (Set[int]): Numeric days of the month (1–31).

    """

    days_of_month: set[int]

    def __post_init__(self) -> None:
        """Validate the invariants for numeric month days.

        Raises:
            InvalidMonthDayValue: If `days_of_month` is empty or contains
            values outside the valid range (1–31).
        """

        super().__post_init__()
        object.__setattr__(self, "_freq", "MONTHLY")

        if not self.days_of_month:
            raise InvalidMonthDayValue("days_of_month cannot be empty.")

        # Validate that all provided days are within 1–31
        invalids: list[int] = [d for d in self.days_of_month if not (1 <= d <= 31)]
        if invalids:
            raise InvalidMonthDayValue(str(invalids))

    def _rrule_extra_parts(self) -> list[str]:
        """Generate BYMONTHDAY part for RFC 5545 RRULE string.

        Returns:
            list[str]: A list containing the BYMONTHDAY clause with
            the specified days of the month.
        """
        days_str = ",".join(str(d) for d in sorted(self.days_of_month))
        return [f"BYMONTHDAY={days_str}"]

    def describe_pattern(self) -> str:
        """Describe the rule: "Every month on days 10 and 20"."""

        label: str = "day" if len(self.days_of_month) == 1 else "days"
        days: str = join_naturally(str(d) for d in sorted(self.days_of_month))
        return f"{self._every('month')} on {label} {days}"

    def get_first_valid_occurrence(self) -> datetime:
        """
        Locate the first allowed date (day of the
        month) equal to or later than start_date.
        """

        base_dt: datetime = self.start_date.materialize()

        # Normalize to ensure correct comparison (timezone/naive)
        start_norm = self.normalize_comparison_date(base_dt)

        scan_year = start_norm.year
        scan_month = start_norm.month

        # Search horizon of 120 months
        for _ in range(120):
            max_days = calendar.monthrange(scan_year, scan_month)[1]
            # Selected days that exist in this specific month
            valid_days = sorted([d for d in self.days_of_month if d <= max_days])

            for day in valid_days:
                candidate_date = date(scan_year, scan_month, day)
                candidate = self._combine_with_start_time(candidate_date)

                # The first occurrence must be greater than or equal to start_date
                if candidate >= start_norm:
                    return candidate

            # If no day in the current month is valid,
            # calculate the next valid month based on the interval
            months_since_start = (scan_year - base_dt.year) * 12 + (
                scan_month - base_dt.month
            )
            months_to_advance = self.interval - (months_since_start % self.interval)

            total_months = scan_month - 1 + months_to_advance
            scan_year += total_months // 12
            scan_month = (total_months % 12) + 1

        return base_dt

    def get_next_occurrence(
        self, last_occurrence: datetime | None = None
    ) -> datetime | None:
        """Calculate the next occurrence scanning through valid month days.

        If no `last_occurrence` is provided, the first valid occurrence is returned.
        Otherwise, the method scans month by month (up to 120 months ahead) to
        find the next valid day of the month that matches the recurrence rule.

        Args:
            last_occurrence (Optional[datetime], optional): The last occurrence
                to continue from. Defaults to None.

        Returns:
            Optional[datetime]: The next valid occurrence if available,
            otherwise None.
        """

        base_dt: datetime = self.start_date.materialize()

        if last_occurrence is None:
            first = self.get_first_valid_occurrence()
            return first if not self._is_exhausted(first) else None

        last: datetime = self.normalize_comparison_date(last_occurrence)

        # Start scanning from the month of the last occurrence
        scan_year: int = last.year
        scan_month: int = last.month

        # Safety limit (120 months = 10 years) to avoid infinite loops
        for _ in range(120):
            max_days_in_month: int = calendar.monthrange(scan_year, scan_month)[1]
            valid_days: list[int] = sorted(self.days_of_month)

            # 1. Look for a valid day in the current month of the loop
            for day in valid_days:
                # Ignore days that do not exist in this month (e.g., Feb 30)
                if day <= max_days_in_month:
                    candidate_date: date = date(scan_year, scan_month, day)
                    candidate: datetime = self._combine_with_start_time(candidate_date)

                    # Candidate must be strictly in the future
                    if candidate > last:
                        if self._is_exhausted(candidate):
                            return None
                        return candidate

            # 2. If no valid day was found in this month, advance to the next
            # valid month, respecting the `interval` (e.g., every 2 months)

            # Calculate the difference in months relative
            # to start_date to maintain cadence
            months_diff: int = (scan_year - base_dt.year) * 12 + (
                scan_month - base_dt.month
            )
            remainder: int = months_diff % self.interval
            months_to_advance: int = self.interval - remainder

            # Safe math to overflow into years if necessary
            new_month = scan_month - 1 + months_to_advance
            scan_year += new_month // 12
            scan_month = (new_month % 12) + 1

        return None
