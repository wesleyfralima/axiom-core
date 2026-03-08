import calendar
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional, Set

from b_domain.exceptions.recurrence import InvalidMonthDayValue
from b_domain.value_objects.recurrences import RecurrenceRule


@dataclass(frozen=True, kw_only=True)
class MonthlyByDaysRule(RecurrenceRule):
    """Rule for occurrences on specific numeric days of the month.

    Handles recurrences like "Every 10th and 20th of the month".
    If a specified day exceeds the number of days in a given month
    (e.g., day 31 in February), that specific day is safely ignored for that month.

    Attributes:
        days_of_month (Set[int]): Numeric days of the month (1-31).
    """

    days_of_month: Set[int]

    def __post_init__(self) -> None:
        """Validate the invariants for numeric month days."""

        super().__post_init__()

        if not self.days_of_month:
            raise InvalidMonthDayValue("days_of_month cannot be empty.")

        invalids: list[int] = [d for d in self.days_of_month if not (1 <= d <= 31)]
        if invalids:
            raise InvalidMonthDayValue(str(invalids))

    @property
    def rrule_string(self) -> str:
        """Generates the RFC 5545 string specifically for monthly day recurrence."""
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

        # Add the specific month days, ordered
        days_str = ",".join(str(d) for d in sorted(self.days_of_month))
        parts.append(f"BYMONTHDAY={days_str}")

        return f"RRULE:{';'.join(parts)}"

    def get_first_valid_occurrence(self) -> datetime:
        """
        Localiza a primeira data permitida (dia do mês) igual ou posterior à start_date.
        """

        # Normalizamos para garantir comparação correta (timezone/naive)
        start_norm = self._normalize_comparison_date(self.start_date)

        scan_year = start_norm.year
        scan_month = start_norm.month

        # Horizonte de busca de 120 meses
        for _ in range(120):
            max_days = calendar.monthrange(scan_year, scan_month)[1]
            # Dias selecionados que existem neste mês específico
            valid_days = sorted([d for d in self.days_of_month if d <= max_days])

            for day in valid_days:
                candidate_date = date(scan_year, scan_month, day)
                candidate = self._combine_with_start_time(candidate_date)

                # A primeira ocorrência deve ser maior ou igual a start_date
                if candidate >= start_norm:
                    return candidate

            # Se nenhum dia do mês atual servir, calcula o próximo mês válido pelo intervalo
            months_since_start = (scan_year - self.start_date.year) * 12 + (scan_month - self.start_date.month)
            months_to_advance = self.interval - (months_since_start % self.interval)

            total_months = scan_month - 1 + months_to_advance
            scan_year = scan_year + (total_months // 12)
            scan_month = (total_months % 12) + 1

        return self.start_date

    def get_next_occurrence(self, last_occurrence: Optional[datetime] = None) -> Optional[datetime]:
        """Calculates the next occurrence scanning through valid month days."""

        if last_occurrence is None:
            first = self.get_first_valid_occurrence()
            return first if not self._is_exhausted(first) else None

        last = self._normalize_comparison_date(last_occurrence)

        # Inicia a busca a partir do mês da última ocorrência
        scan_year = last.year
        scan_month = last.month

        # Limite de segurança (120 meses = 10 anos) para evitar loops infinitos
        for _ in range(120):
            max_days_in_month = calendar.monthrange(scan_year, scan_month)[1]
            valid_days = sorted(self.days_of_month)

            # 1. Procura um dia válido no mês atual do loop
            for day in valid_days:
                # Ignora dias que não existem neste mês (ex: 30/02)
                if day <= max_days_in_month:
                    candidate_date = date(scan_year, scan_month, day)
                    candidate = self._combine_with_start_time(candidate_date)

                    # O candidato tem de ser estritamente no futuro
                    if candidate > last:
                        if self._is_exhausted(candidate):
                            return None
                        return candidate

            # 2. Se não encontrou nenhum dia válido neste mês, avança para o próximo
            # mês válido, respeitando o `interval` (ex: a cada 2 meses)

            # Calcula a diferença de meses em relação à start_date para manter a cadência correta
            months_diff = (scan_year - self.start_date.year) * 12 + (scan_month - self.start_date.month)
            remainder = months_diff % self.interval
            months_to_advance = self.interval - remainder

            # Matemática segura para transbordar anos se necessário
            new_month = scan_month - 1 + months_to_advance
            scan_year = scan_year + (new_month // 12)
            scan_month = (new_month % 12) + 1

        return None
