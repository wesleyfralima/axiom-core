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
        """Validate the specific invariants for weekly rules."""
        super().__post_init__()

        if not self.days_of_week:
            raise InvalidWeekDayValue("days_of_week cannot be empty.")

        invalids = [d for d in self.days_of_week if not (0 <= d <= 6)]
        if invalids:
            raise InvalidWeekDayValue(str(invalids))

    @property
    def rrule_string(self) -> str:
        """Generates the RFC 5545 string specifically for weekly recurrence."""

        parts = ["FREQ=WEEKLY"]

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
        Calcula a primeira ocorrência válida.
        Pode ser a própria start_date ou o próximo dia permitido na semana.
        """

        # 1. Normalizamos a data de início para a lógica de comparação
        start_norm = self._normalize_comparison_date(self.start_date)

        # 2. Encontramos o início da semana (segunda-feira) da start_date
        week_start = start_norm - timedelta(days=start_norm.weekday())

        # 3. Procuramos o primeiro dia da lista 'days_of_week' que seja maior ou igual a start_date
        valid_days = sorted(self.days_of_week)
        for day_idx in valid_days:
            candidate_date = (week_start + timedelta(days=day_idx)).date()
            candidate = self._combine_with_start_time(candidate_date)

            if candidate >= start_norm:
                return candidate

        # 4. Caso a start_date seja após todos os dias selecionados naquela semana,
        # avançamos para a próxima semana válida baseada no intervalo.
        next_week_start = week_start + timedelta(weeks=self.interval)
        candidate_date = (next_week_start + timedelta(days=valid_days[0])).date()
        return self._combine_with_start_time(candidate_date)

    def get_next_occurrence(self, last_occurrence: Optional[datetime] = None) -> Optional[datetime]:
        """Calculates the next occurrence considering the specified weekdays."""

        # 1. Base case: First occurrence
        if last_occurrence is None:
            first = self.get_first_valid_occurrence()
            if self._is_exhausted(first):
                return None
            return first

        # 2. Normalize timezone for math
        last = self._normalize_comparison_date(last_occurrence)
        valid_days = sorted(self.days_of_week)

        # 3. Find week boundaries (Monday as start of week)
        last_week_start = last - timedelta(days=last.weekday())

        # Normalizamos também a start_date para encontrar a semana âncora
        start_norm = self._normalize_comparison_date(self.start_date)
        start_week_start = start_norm - timedelta(days=start_norm.weekday())

        # 4. Calculate how many full weeks have passed since the anchor week
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

        # 6. Advance to the NEXT valid week based on the interval
        remainder = weeks_diff % self.interval
        weeks_to_advance = self.interval - remainder
        next_week_start = last_week_start + timedelta(weeks=weeks_to_advance)

        # Return the first valid day of that new week
        candidate_date = (next_week_start + timedelta(days=valid_days[0])).date()
        candidate = self._combine_with_start_time(candidate_date)

        if self._is_exhausted(candidate):
            return None

        return candidate
