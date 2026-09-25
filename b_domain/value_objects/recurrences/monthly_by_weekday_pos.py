import calendar
from dataclasses import dataclass
from datetime import date, datetime

from a_core.exceptions import ValidationException
from b_domain.exceptions.recurrence import InvalidWeekDayValue
from b_domain.value_objects.recurrences import RecurrenceRule


@dataclass(frozen=True, kw_only=True)
class MonthlyWeekdayPositionalRule(RecurrenceRule):
    """Rule for occurrences on the N-th specific weekday(s) of the month.

    Handles recurrences like "The 2nd Friday of the month" or
    "The last Monday and Wednesday of the month".

    Attributes:
        days_of_week (Set[int]): Weekdays to repeat on (0=Monday, 6=Sunday).
        set_pos (int): The positional index (e.g., 1 for 1st, 2 for 2nd, -1 for last).
            Cannot be 0. Normally between -5 and 5.
    """

    days_of_week: set[int]
    set_pos: int

    def __post_init__(self) -> None:
        """Validate the specific invariants for positioned weekdays.

        Raises:
            InvalidWeekDayValue: If `days_of_week` is empty or contains invalid values.
            ValidationException: If `set_pos` is 0 or outside the valid range (-5 to 5).
        """

        super().__post_init__()
        object.__setattr__(self, "_freq", "MONTHLY")

        if not self.days_of_week:
            raise InvalidWeekDayValue("days_of_week cannot be empty.")

        # Ensure all weekdays are within 0–6 (Monday–Sunday)
        if any(d < 0 or d > 6 for d in self.days_of_week):
            raise InvalidWeekDayValue(
                f"Invalid weekdays: {self.days_of_week}. Must be 0-6."
            )

        if self.set_pos == 0:
            raise ValidationException("Positional index (set_pos) cannot be 0.")

        # A month can have at most 5 occurrences of a specific weekday
        if self.set_pos < -5 or self.set_pos > 5:
            raise ValidationException(
                "Positional weekday index must be between -5 and 5."
            )

    def _rrule_extra_parts(self) -> list[str]:
        """Generate BYDAY part for RFC 5545 RRULE string.

        This method maps the numeric weekdays (0=Monday, 6=Sunday) into
        RFC 5545 weekday abbreviations (MO, TU, WE, TH, FR, SA, SU),
        and combines them with the positional index (`set_pos`).

        Returns:
            list[str]: A list containing the BYDAY clause with positional weekdays.
        """

        # Mapping from numeric weekdays (0–6) to RFC 5545 abbreviations
        day_map: list[str] = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]

        # Build the BYDAY string with positional index applied to each weekday
        days_str: str = ",".join(
            f"{self.set_pos}{day_map[d]}" for d in sorted(self.days_of_week)
        )

        return [f"BYDAY={days_str}"]

    def get_first_valid_occurrence(self) -> datetime:
        """
        Locate the first occurrence that satisfies the ordinal position (set_pos)
        on the chosen weekdays, starting from start_date.
        """

        base_dt: datetime = self.start_date.materialize()
        start_norm: datetime = self.normalize_comparison_date(base_dt)

        scan_year: int = start_norm.year
        scan_month: int = start_norm.month

        # Search within a reasonable horizon (considering the interval)
        for _ in range(120):

            last_day_of_month: int = calendar.monthrange(scan_year, scan_month)[1]
            candidates: list[datetime] = []

            for wd in self.days_of_week:
                # All days in the month that fall on the weekday 'wd'
                days_matching: list[int] = [
                    day
                    for day in range(1, last_day_of_month + 1)
                    if date(scan_year, scan_month, day).weekday() == wd
                ]

                try:
                    # Apply set_pos (e.g., 2 for second occurrence, -1 for last)
                    idx: int = self.set_pos - 1 if self.set_pos > 0 else self.set_pos
                    target_day: int = days_matching[idx]

                    candidate_dt: date = date(scan_year, scan_month, target_day)
                    candidate: datetime = self._combine_with_start_time(candidate_dt)

                    # The occurrence must be greater than or equal to start_date
                    if candidate >= start_norm:
                        candidates.append(candidate)
                except IndexError:
                    # If the requested position does not exist in this month, skip
                    continue

            if candidates:
                # Return the closest occurrence (e.g.,
                # between 2nd Monday and 2nd Friday)
                return min(candidates)

            # If no valid date exists in this month, advance according to the interval
            # (Month skipping logic to ensure alignment with start_date)
            months_since_start: int = (scan_year - base_dt.year) * 12 + (
                scan_month - base_dt.month
            )
            months_to_advance: int = self.interval - (
                months_since_start % self.interval
            )

            total_months: int = scan_month - 1 + months_to_advance
            scan_year += total_months // 12
            scan_month = (total_months % 12) + 1

        return base_dt  # Safety fallback

    def get_next_occurrence(
        self, last_occurrence: datetime | None = None
    ) -> datetime | None:
        """Calculate the next occurrence by finding the N-th target weekdays.

        If no `last_occurrence` is provided, the first valid occurrence is returned.
        Otherwise, the method scans month by month (up to 120 months ahead) to find
        the next valid weekday occurrence based on the positional index (`set_pos`).

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

        scan_year: int = last.year
        scan_month: int = last.month

        # Safety limit (120 months) to prevent infinite loops
        for _ in range(120):

            last_day_of_month: int = calendar.monthrange(scan_year, scan_month)[1]
            month_candidates: list[datetime] = []

            # 1. Find the N-th occurrence for EACH requested weekday in this month
            for wd in self.days_of_week:
                # Gather all dates in the month that fall on this specific weekday
                days_matching: list[int] = [
                    day_num
                    for day_num in range(1, last_day_of_month + 1)
                    if date(scan_year, scan_month, day_num).weekday() == wd
                ]

                try:
                    # Apply the positional index (1-based -> 0-based for lists)
                    if self.set_pos > 0:
                        target_day = days_matching[self.set_pos - 1]
                    else:
                        target_day = days_matching[self.set_pos]

                    candidate_date: date = date(scan_year, scan_month, target_day)
                    candidate: datetime = self._combine_with_start_time(candidate_date)

                    # Only keep candidates strictly in the future
                    if candidate > last:
                        month_candidates.append(candidate)

                except IndexError:
                    # Example: looking for the 5th Monday, but this month only has 4.
                    # Safe to ignore and continue.
                    continue

            if month_candidates:
                # 2. If valid candidates were found in this month
                # (e.g., 2nd Monday and 2nd Friday), return the EARLIEST
                # one to maintain chronological order.
                best_candidate: datetime = min(month_candidates)

                if self._is_exhausted(best_candidate):
                    return None

                return best_candidate

            # 3. Advance to the next valid month based on interval
            months_diff: int = (scan_year - base_dt.year) * 12 + (
                scan_month - base_dt.month
            )
            remainder: int = months_diff % self.interval
            months_to_advance: int = self.interval - remainder

            new_month: int = scan_month - 1 + months_to_advance
            scan_year += new_month // 12
            scan_month = (new_month % 12) + 1

        return None
