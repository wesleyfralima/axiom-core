from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Optional

from a_core.exceptions import ValidationException
from b_domain.value_objects.recurrences import RecurrenceRule


@dataclass(frozen=True, kw_only=True)
class HourlyWindowRule(RecurrenceRule):
    """Rule for hourly occurrences strictly within a daily time window.

    Perfect for habits (e.g., "Drink water every 2 hours between 08:00 and 20:00").
    When an interval pushes the next occurrence past the `window_end`, it automatically
    wraps around to the `window_start` of the next day.

    Attributes:
        window_start (time): The earliest allowed time for an event in a day.
        window_end (time): The latest allowed time for an event in a day.
    """

    window_start: time
    window_end: time

    def __post_init__(self) -> None:
        """Validate the hourly window invariants.

        Raises:
            ValidationException: If window_start >= window_end,
            if minutes are not aligned to full hours,
            or if interval exceeds 24 hours.
        """

        super().__post_init__()
        object.__setattr__(self, "_freq", "HOURLY")

        if self.window_start >= self.window_end:
            raise ValidationException("window_start must be strictly before window_end.")

        if self.window_start.minute != 0 or self.window_end.minute != 0:
            raise ValidationException("window must align to full hours")

        if self.interval > 24:
            raise ValidationException("Hourly interval should not exceed 24 hours.")

    def _rrule_extra_parts(self) -> list[str]:
        """Generate BYHOUR parts for RFC 5545 RRULE string.

        Returns:
            list[str]: A list containing the BYHOUR clause with allowed hours.
        """

        hours: list[str] = []
        current: int = self.window_start.hour
        end: int = self.window_end.hour

        while current <= end:
            hours.append(str(current))
            current += self.interval

        return [f"BYHOUR={','.join(hours)}"]

    def _apply_start_tz(self, dt: datetime) -> datetime:
        """Helper to reapply the timezone of `start_date`.

        Ensures that generated candidate datetimes inherit the timezone
        information from the rule's `start_date` if available.

        Args:
            dt (datetime): The candidate datetime.

        Returns:
            datetime: The candidate datetime with the rule's timezone reapplied.
        """
        base_dt: datetime = self.start_date.materialize()
        if base_dt.tzinfo:
            return dt.replace(tzinfo=base_dt.tzinfo)
        return dt

    def get_first_valid_occurrence(self) -> datetime:
        """
        Locate the first valid occurrence respecting the defined daily window.
        """

        base_dt: datetime = self.start_date.materialize()
        start_norm = self._normalize_comparison_date(base_dt)
        start_time = start_norm.time()

        # 1. If start_date is before the window on the same day:
        # Adjust to window_start of the same day.
        if start_time < self.window_start:
            candidate = datetime.combine(start_norm.date(), self.window_start)
            return self._apply_start_tz(candidate)

        # 2. If start_date is inside the window:
        # It is itself the first valid occurrence.
        if self.window_start <= start_time <= self.window_end:
            return start_norm

        # 3. If start_date is after window_end:
        # Move to window_start of the next day.
        next_day = start_norm.date() + timedelta(days=1)
        candidate = datetime.combine(next_day, self.window_start)
        return self._apply_start_tz(candidate)

    def get_next_occurrence(self, last_occurrence: Optional[datetime] = None) -> Optional[datetime]:
        """Calculate the next occurrence, respecting the defined daily window.

        If no `last_occurrence` is provided, the first valid occurrence is returned.
        Otherwise, the method increments by the defined interval and applies
        wrap‑around logic when the candidate exceeds the daily window.

        Args:
            last_occurrence (Optional[datetime], optional): The last occurrence
                to continue from. Defaults to None.

        Returns:
            Optional[datetime]: The next valid occurrence if available,
            otherwise None.
        """

        # 1. Base case: Find the first valid occurrence within the window
        if last_occurrence is None:
            first = self.get_first_valid_occurrence()
            return first if not self._is_exhausted(first) else None

        # 2. Increment logic (original steps)
        last = self._normalize_comparison_date(last_occurrence)
        candidate = last + timedelta(hours=self.interval)

        # 3. Wrap-around logic
        if (
                candidate.time() > self.window_end or
                (candidate.time() < self.window_start and candidate.date() > last.date())
        ):
            next_day = last.date() + timedelta(days=1)
            candidate = datetime.combine(next_day, self.window_start)
            candidate = self._apply_start_tz(candidate)

        if self._is_exhausted(candidate):
            return None

        return candidate
