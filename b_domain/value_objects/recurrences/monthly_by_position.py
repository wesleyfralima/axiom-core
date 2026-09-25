import calendar
from dataclasses import dataclass
from datetime import date, datetime

from a_core.exceptions import ValidationException
from a_core.text import ordinal_phrase
from b_domain.value_objects.recurrences import RecurrenceRule


@dataclass(frozen=True, kw_only=True)
class MonthlyPositionalRule(RecurrenceRule):
    """Rule for occurrences based on a relative position in the month.

    Handles recurrences like "The last day of the month" (set_pos = -1) or
    "The 5th day from the end of the month" (set_pos = -5).

    Attributes:
        set_pos (int): The positional index. Positive values count from the
            start of the month (1 = 1st day), negative values count from the
            end of the month (-1 = last day). Cannot be 0.
    """

    set_pos: int

    def __post_init__(self) -> None:
        """Validate the positional invariant.

        Raises:
            ValidationException: If `set_pos` is 0 or
                outside the valid range (-31 to 31).
        """

        super().__post_init__()
        object.__setattr__(self, "_freq", "MONTHLY")

        if self.set_pos == 0:
            raise ValidationException("Positional index (set_pos) cannot be 0.")

        # Ensure the positional index is within realistic bounds
        if self.set_pos < -31 or self.set_pos > 31:
            raise ValidationException("Positional index must be between -31 and 31.")

    def _rrule_extra_parts(self) -> list[str]:
        """Generate BYMONTHDAY part for RFC 5545 RRULE string.

        Returns:
            list[str]: A list containing the BYMONTHDAY
                clause with the positional index.
        """
        return [f"BYMONTHDAY={self.set_pos}"]

    def describe_pattern(self) -> str:
        """Describe the rule: "Every month on day 15", "… on the last day"."""

        if self.set_pos > 0:
            return f"{self._every('month')} on day {self.set_pos}"
        return f"{self._every('month')} on the {ordinal_phrase(self.set_pos)} day"

    def get_first_valid_occurrence(self) -> datetime:
        """
        Calculate the first valid date based on the relative position (e.g., last day).
        Ensures that the date is equal to or later than start_date.
        """

        base_dt: datetime = self.start_date.materialize()
        start_norm = self.normalize_comparison_date(base_dt)

        scan_year = start_norm.year
        scan_month = start_norm.month

        # Search horizon of 120 months
        for _ in range(120):
            last_day_of_month = calendar.monthrange(scan_year, scan_month)[1]

            # 1. Calculate the actual day based on set_pos
            if self.set_pos > 0:
                # If requesting day 31 in February, clamp to day 28/29
                day = min(self.set_pos, last_day_of_month)
            else:
                # Negative logic: -1 becomes the last day of the month
                day = last_day_of_month + self.set_pos + 1

            if day >= 1:
                candidate_date = date(scan_year, scan_month, day)
                candidate = self._combine_with_start_time(candidate_date)

                # The first occurrence must be greater than or equal to start_date
                if candidate >= start_norm:
                    return candidate

            # 2. If the calculated position for this month has already passed,
            # advance by the interval
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
        """Calculate the next occurrence based on relative month positioning.

        If no `last_occurrence` is provided, the first valid occurrence is returned.
        Otherwise, the method scans month by month (up to 120 months ahead) to
        find the next valid date based on the positional index (`set_pos`).

        Args:
            last_occurrence (Optional[datetime], optional): The last occurrence
                to continue from. Defaults to None.

        Returns:
            Optional[datetime]: The next valid occurrence if available,
            otherwise None.
        """

        base_dt: datetime = self.start_date.materialize()

        if last_occurrence is None:
            first: datetime = self.get_first_valid_occurrence()
            return first if not self._is_exhausted(first) else None

        last: datetime = self.normalize_comparison_date(last_occurrence)

        scan_year: int = last.year
        scan_month: int = last.month
        day: int

        # Safety limit (120 months = 10 years) to prevent infinite loops
        for _ in range(120):

            last_day_of_month: int = calendar.monthrange(scan_year, scan_month)[1]

            # 1. Calculate the exact calendar day based on the positional index
            if self.set_pos > 0:
                # Clamp to the end of the month if the position exceeds it
                # (e.g., 31st position in February becomes the 28th/29th)
                day = min(self.set_pos, last_day_of_month)
            else:
                # Negative indexing (e.g., -1 is the last day)
                day = last_day_of_month + self.set_pos + 1

            # If the negative index asks for a day that doesn't exist (e.g., -35),
            # skip this month
            if day >= 1:
                candidate_date = date(scan_year, scan_month, day)
                candidate = self._combine_with_start_time(candidate_date)

                # 2. Check if we found a valid candidate strictly in the future
                if candidate > last:
                    if self._is_exhausted(candidate):
                        return None
                    return candidate

            # 3. Advance to the next valid month based on the interval
            months_diff: int = (scan_year - base_dt.year) * 12 + (
                scan_month - base_dt.month
            )
            remainder: int = months_diff % self.interval
            months_to_advance: int = self.interval - remainder

            # Safe math to overflow into years if necessary
            new_month: int = scan_month - 1 + months_to_advance
            scan_year += new_month // 12
            scan_month = (new_month % 12) + 1

        return None
