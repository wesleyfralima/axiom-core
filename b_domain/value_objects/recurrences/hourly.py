from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Optional

from a_core.exceptions import ValidationException
from b_domain.value_objects.recurrences import RecurrenceRule


@dataclass(frozen=True, kw_only=True)
class HourlyWindowRule(RecurrenceRule):
    """Rule for hourly occurrences strictly within a daily time window.

    Perfect for habits (e.g., "Drink water every 2 hours between 08:00 and 20:00").
    When an interval pushes the next occurrence past the end_time, it automatically
    wraps around to the start_time of the next day.

    Attributes:
        window_start (time): The earliest allowed time for an event in a day.
        window_end (time): The latest allowed time for an event in a day.
    """

    window_start: time
    window_end: time

    def __post_init__(self) -> None:
        """Validate the hourly window invariants."""

        super().__post_init__()

        if self.window_start >= self.window_end:
            raise ValidationException("window_start must be strictly before window_end.")

        # Ensure the interval makes sense for hours (e.g., not larger than a day)
        if self.interval > 24:
            raise ValidationException("Hourly interval should not exceed 24 hours.")

    @property
    def rrule_string(self) -> str:
        """Generates the RFC 5545 string.

        Note: RFC 5545 doesn't perfectly support "windows" natively with pure INTERVAL.
        We output the basic hourly frequency. Complex windowing in external providers
        usually requires generating individual events or using BYHOUR arrays.
        """

        parts = ["FREQ=HOURLY"]
        if self.interval > 1:
            parts.append(f"INTERVAL={self.interval}")

        if self.count:
            parts.append(f"COUNT={self.count}")
        elif self.end_date:
            fmt = "%Y%m%dT%H%M%S"
            dt_str = self.end_date.strftime(fmt)
            if self.end_date.tzinfo is not None:
                dt_str += "Z"
            parts.append(f"UNTIL={dt_str}")

        return f"RRULE:{';'.join(parts)}"

    def get_first_valid_occurrence(self) -> datetime:
        """
        Localiza a primeira ocorrência válida respeitando a janela horária.
        """

        start_norm = self._normalize_comparison_date(self.start_date)
        start_time = start_norm.time()

        # 1. Se a start_date está antes da janela no mesmo dia:
        # Ajustamos para o window_start do próprio dia.
        if start_time < self.window_start:
            candidate = datetime.combine(start_norm.date(), self.window_start)
            return self._apply_start_tz(candidate)

        # 2. Se a start_date está dentro da janela:
        # Ela mesma é a primeira ocorrência válida.
        if self.window_start <= start_time <= self.window_end:
            return start_norm

        # 3. Se a start_date está após o window_end:
        # Pulamos para o window_start do dia seguinte.
        next_day = start_norm.date() + timedelta(days=1)
        candidate = datetime.combine(next_day, self.window_start)
        return self._apply_start_tz(candidate)

    def _apply_start_tz(self, dt: datetime) -> datetime:
        """Auxiliar para reaplicar o fuso horário da start_date."""
        if self.start_date.tzinfo:
            return dt.replace(tzinfo=self.start_date.tzinfo)
        return dt

    def get_next_occurrence(self, last_occurrence: Optional[datetime] = None) -> Optional[datetime]:
        """Calculates the next occurrence, respecting the daily window."""

        # 1. Base case: Encontra o primeiro momento válido dentro da janela
        if last_occurrence is None:
            first = self.get_first_valid_occurrence()
            return first if not self._is_exhausted(first) else None

        # 2. Lógica de incremento (seus passos originais)
        last = self._normalize_comparison_date(last_occurrence)
        candidate = last + timedelta(hours=self.interval)

        # 3. Lógica de Wrap-around
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
