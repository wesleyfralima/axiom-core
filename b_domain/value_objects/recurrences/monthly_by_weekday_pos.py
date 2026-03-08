import calendar
from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Optional, Set

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

    days_of_week: Set[int]
    set_pos: int

    def __post_init__(self) -> None:
        """Validate the specific invariants for positioned weekdays."""

        super().__post_init__()

        if not self.days_of_week:
            raise InvalidWeekDayValue("days_of_week cannot be empty.")

        if any(d < 0 or d > 6 for d in self.days_of_week):
            raise InvalidWeekDayValue(f"Invalid weekdays: {self.days_of_week}. Must be 0-6.")

        if self.set_pos == 0:
            raise ValidationException("Positional index (set_pos) cannot be 0.")

        if self.set_pos < -5 or self.set_pos > 5:
            # A month can have at most 5 occurrences of a specific weekday.
            raise ValidationException("Positional weekday index must be between -5 and 5.")

    @property
    def rrule_string(self) -> str:
        """Generates the RFC 5545 string.

        Correctly maps the human logic of "2nd Monday and 2nd Friday" to
        the RFC compliant BYDAY=2MO,2FR (instead of using BYSETPOS, which
        has a different global filtering meaning in the spec).
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

        # Map Python's 0-6 to RFC 5545 days and prefix with the set_pos
        # e.g., set_pos=2 and days={0, 4} becomes "2MO,2FR"
        day_map = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
        days_str = ",".join(f"{self.set_pos}{day_map[d]}" for d in sorted(self.days_of_week))
        parts.append(f"BYDAY={days_str}")

        return f"RRULE:{';'.join(parts)}"

    def get_first_valid_occurrence(self) -> datetime:
        """
        Localiza a primeira ocorrência que satisfaz a posição ordinal (set_pos)
        nos dias da semana escolhidos, a partir da start_date.
        """
        start_norm = self._normalize_comparison_date(self.start_date)

        scan_year = start_norm.year
        scan_month = start_norm.month

        # Buscamos em um horizonte de tempo razoável (considerando o intervalo)
        for _ in range(120):
            last_day_of_month = calendar.monthrange(scan_year, scan_month)[1]
            candidates: List[datetime] = []

            for wd in self.days_of_week:
                # Todos os dias do mês que caem no dia da semana 'wd'
                days_matching = [
                    day for day in range(1, last_day_of_month + 1)
                    if date(scan_year, scan_month, day).weekday() == wd
                ]

                try:
                    # Aplica o set_pos (ex: 2 para segunda ocorrência, -1 para última)
                    idx = self.set_pos - 1 if self.set_pos > 0 else self.set_pos
                    target_day = days_matching[idx]

                    candidate_dt = date(scan_year, scan_month, target_day)
                    candidate = self._combine_with_start_time(candidate_dt)

                    # A ocorrência deve ser maior ou igual a start_date
                    if candidate >= start_norm:
                        candidates.append(candidate)
                except IndexError:
                    continue

            if candidates:
                # Retornamos a mais próxima (ex: entre 2ª segunda e 2ª sexta)
                return min(candidates)

            # Se não houver data válida neste mês, avança conforme o intervalo
            # (Lógica de salto de meses para garantir alinhamento com a start_date)
            months_since_start = (scan_year - self.start_date.year) * 12 + (scan_month - self.start_date.month)
            months_to_advance = self.interval - (months_since_start % self.interval)

            total_months = scan_month - 1 + months_to_advance
            scan_year = scan_year + (total_months // 12)
            scan_month = (total_months % 12) + 1

        return self.start_date  # Fallback de segurança

    def get_next_occurrence(self, last_occurrence: Optional[datetime] = None) -> Optional[datetime]:
        """Calculates the next occurrence by finding the N-th target weekdays."""

        if last_occurrence is None:
            first = self.get_first_valid_occurrence()
            return first if not self._is_exhausted(first) else None

        last = self._normalize_comparison_date(last_occurrence)

        scan_year = last.year
        scan_month = last.month

        # Safety limit (120 months)
        for _ in range(120):
            last_day_of_month = calendar.monthrange(scan_year, scan_month)[1]
            month_candidates: List[datetime] = []

            # Find the N-th occurrence for EACH requested weekday in this month
            for wd in self.days_of_week:
                # Gather all dates in the month that fall on this specific weekday
                days_matching = [
                    day_num for day_num in range(1, last_day_of_month + 1)
                    if date(scan_year, scan_month, day_num).weekday() == wd
                ]

                try:
                    # Apply the positional index (1-based -> 0-based for lists)
                    if self.set_pos > 0:
                        target_day = days_matching[self.set_pos - 1]
                    else:
                        target_day = days_matching[self.set_pos]

                    candidate_date = date(scan_year, scan_month, target_day)
                    candidate = self._combine_with_start_time(candidate_date)

                    # Only keep candidates strictly in the future
                    if candidate > last:
                        month_candidates.append(candidate)

                except IndexError:
                    # e.g., looking for the 5th Monday, but this month only has 4.
                    # Safe to ignore and continue.
                    continue

            if month_candidates:
                # If we found valid candidates in this month (e.g. 2nd Monday and 2nd Friday)
                # we must return the EARLIEST one to maintain chronological order.
                best_candidate = min(month_candidates)

                if self._is_exhausted(best_candidate):
                    return None
                return best_candidate

            # Advance to the next valid month based on interval
            months_diff = (scan_year - self.start_date.year) * 12 + (scan_month - self.start_date.month)
            remainder = months_diff % self.interval
            months_to_advance = self.interval - remainder

            new_month = scan_month - 1 + months_to_advance
            scan_year = scan_year + (new_month // 12)
            scan_month = (new_month % 12) + 1

        return None
