import calendar
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from a_core.exceptions import ValidationException
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
        """Validate the positional invariant."""

        super().__post_init__()

        if self.set_pos == 0:
            raise ValidationException("Positional index (set_pos) cannot be 0.")

        if self.set_pos < -31 or self.set_pos > 31:
            raise ValidationException("Positional index must be between -31 and 31.")

    @property
    def rrule_string(self) -> str:
        """Generates the RFC 5545 string.

        Note: According to RFC 5545, a simple positional day of the month
        translates to BYMONTHDAY, not BYSETPOS (which requires another BY-rule).
        """

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

        # Map the positional logic to BYMONTHDAY (e.g., -1 for last day)
        parts.append(f"BYMONTHDAY={self.set_pos}")

        return f"RRULE:{';'.join(parts)}"

    def get_first_valid_occurrence(self) -> datetime:
        """
        Calcula a primeira data válida baseada na posição relativa (ex: último dia).
        Garante que a data seja igual ou posterior à start_date.
        """

        start_norm = self._normalize_comparison_date(self.start_date)

        scan_year = start_norm.year
        scan_month = start_norm.month

        # Busca em um horizonte de 120 meses
        for _ in range(120):
            last_day_of_month = calendar.monthrange(scan_year, scan_month)[1]

            # 1. Calcula o dia real baseado no set_pos
            if self.set_pos > 0:
                # Se pedir dia 31 em fevereiro, clamp para o dia 28/29
                day = min(self.set_pos, last_day_of_month)
            else:
                # Lógica negativa: -1 vira o último dia do mês
                day = last_day_of_month + self.set_pos + 1

            if day >= 1:
                candidate_date = date(scan_year, scan_month, day)
                candidate = self._combine_with_start_time(candidate_date)

                # A primeira ocorrência deve ser maior ou igual a start_date
                if candidate >= start_norm:
                    return candidate

            # 2. Se a posição calculada para este mês já passou, avança pelo intervalo
            months_since_start = (scan_year - self.start_date.year) * 12 + (scan_month - self.start_date.month)
            months_to_advance = self.interval - (months_since_start % self.interval)

            total_months = scan_month - 1 + months_to_advance
            scan_year = scan_year + (total_months // 12)
            scan_month = (total_months % 12) + 1

        return self.start_date

    def get_next_occurrence(self, last_occurrence: Optional[datetime] = None) -> Optional[datetime]:
        """Calculates the next occurrence based on relative month positioning."""

        if last_occurrence is None:
            first = self.get_first_valid_occurrence()
            return first if not self._is_exhausted(first) else None

        last = self._normalize_comparison_date(last_occurrence)

        scan_year = last.year
        scan_month = last.month

        # Safety limit (120 months = 10 years) to prevent infinite loops
        for _ in range(120):
            last_day_of_month = calendar.monthrange(scan_year, scan_month)[1]

            # Calculate the exact calendar day based on the positional index
            if self.set_pos > 0:
                # Clamp to the end of the month if the position exceeds it
                # (e.g., 31st position in February becomes the 28th/29th)
                day = min(self.set_pos, last_day_of_month)
            else:
                # Negative indexing (e.g., -1 is the last day)
                day = last_day_of_month + self.set_pos + 1

            # If the negative index asks for a day that doesn't exist (e.g. -35),
            # we skip this month.
            if day >= 1:
                candidate_date = date(scan_year, scan_month, day)
                candidate = self._combine_with_start_time(candidate_date)

                # Check if we found a valid candidate strictly in the future
                if candidate > last:
                    if self._is_exhausted(candidate):
                        return None
                    return candidate

            # Advance to the next valid month based on the interval
            months_diff = (scan_year - self.start_date.year) * 12 + (scan_month - self.start_date.month)
            remainder = months_diff % self.interval
            months_to_advance = self.interval - remainder

            new_month = scan_month - 1 + months_to_advance
            scan_year = scan_year + (new_month // 12)
            scan_month = (new_month % 12) + 1

        return None
