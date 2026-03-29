import calendar
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable, Optional

from a_core import ValidationException
from b_domain.value_objects.recurrences import RecurrenceRule


@dataclass(frozen=True, kw_only=True)
class BusinessDayRule(RecurrenceRule):
    """Rule for occurrences on the N-th business day of the month.

    Handles recurrences like "The 5th business day of the month" or
    "The last business day of the month". Requires an external checker
    to determine what constitutes a business day (skipping weekends/holidays).

    Attributes:
        nth_day (int): The business day index (e.g., 5 for 5th, -1 for last).
        is_business_day (Callable[[date], bool]): Function injected to validate dates.
            Excluded from equality comparisons to maintain Value Object purity.
    """

    nth_day: int
    is_business_day: Callable[[date], bool] = field(compare=False, repr=False)

    def __post_init__(self) -> None:
        """Validate the specific invariants for business days.

        Raises:
            ValidationException: If nth_day is 0, outside realistic bounds,
            or if the callback is missing.
        """
        super().__post_init__()

        if self.nth_day == 0:
            raise ValidationException("Business day index (nth_day) cannot be 0.")

        if self.nth_day < -31 or self.nth_day > 31:
            raise ValidationException("Business day index must be realistically between -31 and 31.")

        if not self.is_business_day:
            raise ValidationException("Callback is_business_day missing.")

    def supports_native_sync(self) -> bool:
        """Business day rules are not natively supported by RFC 5545 RRULEs.

        This is because they depend on variable holiday calendars and
        require external logic to determine valid business days.

        Returns:
            bool: Always False, since RFC 5545 cannot represent business day rules.
        """
        return False

    @property
    def rrule_string(self) -> str:
        """Generates the RFC 5545 string.

        WARNING: RFC 5545 does NOT natively support "business days" because
        holidays vary wildly by country/region. Returning an empty string
        signals to the application (or external sync adapters) that this rule
        cannot be blindly sent to Calendar Providers as an RRULE.

        To sync this with Calendar Providers, the application layer should generate
        the next X dates using `get_next_n_occurrences` and send them as individual
        events or use RDATE properties.
        """

        return ""

    def get_first_valid_occurrence(self) -> datetime | None:
        """Locate the first valid N-th business day occurrence starting from `start_date`.

        This method scans month by month (up to 12 months ahead) to find the
        first valid occurrence that matches the requested business day index
        (`nth_day`). It uses the injected `is_business_day` callback to filter
        valid business days and applies the recurrence interval logic to skip
        months when necessary.

        Returns:
            Optional[datetime]: The first valid occurrence datetime if found,
            otherwise None.

        Raises:
            IndexError: If the requested `nth_day` exceeds the number of business
            days in a given month (caught internally and skipped).
        """

        base_dt: datetime = self.start_date.materialize()
        start_norm = self._normalize_comparison_date(base_dt)

        scan_year = start_norm.year
        scan_month = start_norm.month

        # Search horizon: 12 months (cannot advance more than a year since logic is monthly)
        for _ in range(12):
            last_day_of_month = calendar.monthrange(scan_year, scan_month)[1]

            # 1. Collect business days for the current month
            business_days = [
                date(scan_year, scan_month, d)
                for d in range(1, last_day_of_month + 1)
                if self.is_business_day(date(scan_year, scan_month, d))
            ]

            if business_days:
                try:
                    # 2. Apply index (e.g., 5th business day or last = -1)
                    idx = self.nth_day - 1 if self.nth_day > 0 else self.nth_day
                    target_date = business_days[idx]
                    candidate = self._combine_with_start_time(target_date)

                    # 3. Occurrence must be >= start_date
                    if candidate >= start_norm:
                        return candidate
                except IndexError:
                    # Month has fewer business days than requested nth_day
                    pass

            # 4. Advance month respecting interval (Anchor Date logic)
            months_since_start = (scan_year - base_dt.year) * 12 + (scan_month - base_dt.month)
            months_to_advance = self.interval - (months_since_start % self.interval)

            total_months = scan_month - 1 + months_to_advance
            scan_year = scan_year + (total_months // 12)
            scan_month = (total_months % 12) + 1

        # Safety fallback (though the above logic is exhaustive)
        return None

    def get_next_occurrence(self, last_occurrence: Optional[datetime] = None) -> Optional[datetime]:
        """Calculate the next valid business day occurrence.

        This method scans month by month to find the next valid occurrence
        based on the N-th business day rule. It uses the injected
        `is_business_day` callback to filter valid business days and applies
        recurrence interval logic to skip months when necessary.

        Args:
            last_occurrence (Optional[datetime], optional): The last occurrence
                to continue from. If None, the first valid occurrence is returned.

        Returns:
            Optional[datetime]: The next valid occurrence datetime if found,
            otherwise None.
        """

        if last_occurrence is None:
            first = self.get_first_valid_occurrence()
            return first if not self._is_exhausted(first) else None

        last = self._normalize_comparison_date(last_occurrence)

        scan_year = last.year
        scan_month = last.month

        # Safety limit: scan up to 12 months
        for _ in range(12):
            last_day_of_month = calendar.monthrange(scan_year, scan_month)[1]
            business_days_in_month: list[date] = []

            # 1. Collect all business days of this month
            for day_num in range(1, last_day_of_month + 1):
                d = date(scan_year, scan_month, day_num)
                if self.is_business_day(d):
                    business_days_in_month.append(d)

            # 2. Try to access the requested index (positive or negative)
            try:
                idx = self.nth_day - 1 if self.nth_day > 0 else self.nth_day
                target_date = business_days_in_month[idx]
                candidate = self._combine_with_start_time(target_date)

                # If candidate is in the future, return it
                if candidate > last:
                    if self._is_exhausted(candidate):
                        return None
                    return candidate

            except IndexError:
                # Example: requested 25th business day, but month only had 21
                pass

            # 3. Advance to the next valid month respecting the interval
            base_dt: datetime = self.start_date.materialize()
            months_diff = (scan_year - base_dt.year) * 12 + (scan_month - base_dt.month)
            remainder = months_diff % self.interval
            months_to_advance = self.interval - remainder

            new_month = scan_month - 1 + months_to_advance
            scan_year = scan_year + (new_month // 12)
            scan_month = (new_month % 12) + 1

        return None
