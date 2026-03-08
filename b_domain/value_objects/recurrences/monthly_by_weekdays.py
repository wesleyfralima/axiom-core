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
        """Validate the specific invariants for weekdays."""

        super().__post_init__()

        if not self.days_of_week:
            raise InvalidWeekDayValue("days_of_week cannot be empty.")

        if any(d < 0 or d > 6 for d in self.days_of_week):
            raise InvalidWeekDayValue(f"Invalid weekdays: {self.days_of_week}. Must be 0-6.")

    @property
    def rrule_string(self) -> str:
        """Generates the RFC 5545 string specifically for monthly weekday recurrence."""

        parts = ["FREQ=MONTHLY"]

        if self.interval > 1:
            parts.append(f"INTERVAL={self.interval}")

        if self.count:
            parts.append(f"COUNT={self.count}")
        elif self.end_date:
            dt_str = self.end_date.strftime("%Y%m%dT%H%M%S")
            if self.end_date.tzinfo is not None:
                dt_str += "Z"
            parts.append(f"UNTIL={dt_str}")

        # Map Python's 0-6 (Monday-Sunday) to RFC 5545 days
        day_map = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
        days_str = ",".join(day_map[d] for d in sorted(self.days_of_week))
        parts.append(f"BYDAY={days_str}")

        return f"RRULE:{';'.join(parts)}"

    def get_first_valid_occurrence(self) -> datetime:
        """
        Localiza a primeira ocorrência (dia da semana permitido)
        igual ou posterior à start_date dentro do mês válido.
        """
        start_norm = self._normalize_comparison_date(self.start_date)

        scan_year = start_norm.year
        scan_month = start_norm.month

        # Horizonte de busca de 120 meses
        for _ in range(120):
            last_day_of_month = calendar.monthrange(scan_year, scan_month)[1]

            # Buscamos em todos os dias do mês de scan
            for day_num in range(1, last_day_of_month + 1):
                d = date(scan_year, scan_month, day_num)

                # Se o dia da semana é um dos permitidos
                if d.weekday() in self.days_of_week:
                    candidate = self._combine_with_start_time(d)

                    # A primeira ocorrência deve ser maior ou igual a start_date
                    if candidate >= start_norm:
                        return candidate

            # Se não houver dia válido no mês atual (ou todos já passaram),
            # avança conforme o intervalo (Anchor Date logic)
            months_since_start = (scan_year - self.start_date.year) * 12 + (scan_month - self.start_date.month)
            months_to_advance = self.interval - (months_since_start % self.interval)

            total_months = scan_month - 1 + months_to_advance
            scan_year = scan_year + (total_months // 12)
            scan_month = (total_months % 12) + 1

        return self.start_date

    def get_next_occurrence(self, last_occurrence: Optional[datetime] = None) -> Optional[datetime]:
        """Calculates the next occurrence by iterating through the month's days."""

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

                # Check if the day matches our required weekdays
                if d.weekday() in self.days_of_week:
                    candidate = self._combine_with_start_time(d)

                    # Ensure candidate is strictly in the future
                    if candidate > last:
                        if self._is_exhausted(candidate):
                            return None
                        return candidate

            # 2. Advance to the next valid month based on the interval
            months_diff = (scan_year - self.start_date.year) * 12 + (scan_month - self.start_date.month)
            remainder = months_diff % self.interval
            months_to_advance = self.interval - remainder

            new_month = scan_month - 1 + months_to_advance
            scan_year = scan_year + (new_month // 12)
            scan_month = (new_month % 12) + 1

        return None
