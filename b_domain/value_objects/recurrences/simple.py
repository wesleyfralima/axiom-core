import calendar
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from b_domain.value_objects.enums import RecurrenceInterval
from b_domain.value_objects.recurrences import RecurrenceRule


def add_months(source_date: datetime, months: int, target_day: Optional[int] = None) -> datetime:
    """Add months to a given date, handling end-of-month overflows."""

    month: int = source_date.month - 1 + months
    year: int = source_date.year + month // 12
    month: int = month % 12 + 1

    days_in_new_month: int = calendar.monthrange(year, month)[1]
    original_day_preference: int = target_day if target_day else source_date.day
    day: int = min(original_day_preference, days_in_new_month)

    return source_date.replace(year=year, month=month, day=day)


@dataclass(frozen=True, kw_only=True)
class SimpleIntervalRule(RecurrenceRule):
    """Rule for continuous, simple interval-based recurrences.

    Handles straightforward repetitions like "every 3 days", "every 2 weeks",
    or "every month on the exact same numerical day".

    Attributes:
        frequency (RecurrenceInterval): The unit of the interval (DAILY, WEEKLY, etc.).
    """

    frequency: RecurrenceInterval

    @property
    def rrule_string(self) -> str:
        """Generates the RFC 5545 string for simple intervals."""

        freq_map = {
            RecurrenceInterval.HOURLY: "HOURLY",
            RecurrenceInterval.DAILY: "DAILY",
            RecurrenceInterval.WEEKLY: "WEEKLY",
            RecurrenceInterval.MONTHLY: "MONTHLY",
            RecurrenceInterval.YEARLY: "YEARLY",
        }

        parts = [f"FREQ={freq_map[self.frequency]}"]

        if self.interval > 1:
            parts.append(f"INTERVAL={self.interval}")

        if self.count:
            parts.append(f"COUNT={self.count}")
        elif self.end_date:
            dt_str = self.end_date.strftime("%Y%m%dT%H%M%S")
            if self.end_date.tzinfo is not None:
                dt_str += "Z"
            parts.append(f"UNTIL={dt_str}")

        return f"RRULE:{';'.join(parts)}"

    def get_first_valid_occurrence(self) -> datetime:
        """
        Para intervalos simples, a primeira ocorrência é a própria data de início.
        Diferente de regras semanais ou mensais complexas, não há filtros que
        possam 'empurrar' a primeira data para frente.
        """
        return self.start_date

    def get_next_occurrence(self, last_occurrence: Optional[datetime] = None) -> Optional[datetime]:
        """Calculates the exact next occurrence by adding the interval unit."""

        # 1. Base case: First occurrence
        if last_occurrence is None:
            first = self.get_first_valid_occurrence()
            if self._is_exhausted(first):
                return None
            return first

        # 2. Normalize timezone
        last = self._normalize_comparison_date(last_occurrence)

        # 3. Apply the specific mathematical interval
        candidate = self._add_interval(last)

        # 4. Check global limits (end_date or count)
        if self._is_exhausted(candidate):
            return None

        return candidate

    def _add_interval(self, current: datetime) -> datetime:
        """Executes the specific timedelta math based on the frequency type."""

        if self.frequency == RecurrenceInterval.HOURLY:
            dt = current + timedelta(hours=self.interval)

        elif self.frequency == RecurrenceInterval.DAILY:
            dt = current + timedelta(days=self.interval)

        elif self.frequency == RecurrenceInterval.WEEKLY:
            dt = current + timedelta(weeks=self.interval)

        elif self.frequency == RecurrenceInterval.MONTHLY:
            # Preserva o dia original da start_date como âncora para evitar degradação de datas
            # (Ex: 31 jan -> 28 fev -> volta a tentar o dia 31 em março).
            dt = add_months(current, self.interval, target_day=self.start_date.day)

        elif self.frequency == RecurrenceInterval.YEARLY:
            dt = add_months(current, self.interval * 12, target_day=self.start_date.day)

        else:
            dt = current

        # Garante que o horário original e o timezone (naive/aware) permanecem inalterados
        return self._combine_with_start_time(dt.date())
