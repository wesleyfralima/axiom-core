import calendar
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable, List, Optional

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

    # Injeção de dependência inteligente: não afeta a comparação (==) do Value Object
    # e não polui o print() ou logs (repr=False)
    is_business_day: Callable[[date], bool] = field(compare=False, repr=False)

    def __post_init__(self) -> None:
        """Validate the specific invariants for business days."""

        super().__post_init__()

        if self.nth_day == 0:
            raise ValidationException("Business day index (nth_day) cannot be 0.")

        if self.nth_day < -31 or self.nth_day > 31:
            raise ValidationException("Business day index must be realistically between -31 and 31.")

        if not self.is_business_day:
            raise ValidationException("Callback is_business_day missing.")

    def supports_native_sync(self) -> bool:
        """
        Regras de dias úteis não são suportadas nativamente por RRULEs RFC 5545
        devido à dependência de calendários de feriados variáveis.
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
        """
        Localiza o primeiro N-ésimo dia útil válido a partir da start_date.
        """

        start_norm = self._normalize_comparison_date(self.start_date)

        scan_year = start_norm.year
        scan_month = start_norm.month

        # Horizonte de busca de 12 meses (impossível avançar
        # mais de um ano, pois a lógica é mensal)
        for _ in range(12):
            last_day_of_month = calendar.monthrange(scan_year, scan_month)[1]

            # 1. Coletar dias úteis do mês de scan
            business_days = [
                date(scan_year, scan_month, d)
                for d in range(1, last_day_of_month + 1)
                if self.is_business_day(date(scan_year, scan_month, d))
            ]

            if business_days:
                try:
                    # 2. Aplicar o índice (Ex: 5º dia útil ou último -1)
                    idx = self.nth_day - 1 if self.nth_day > 0 else self.nth_day
                    target_date = business_days[idx]
                    candidate = self._combine_with_start_time(target_date)

                    # 3. A ocorrência deve ser maior ou igual start_date
                    if candidate >= start_norm:
                        return candidate
                except IndexError:
                    # Mês com menos dias úteis que o nth_day solicitado
                    pass

            # 4. Cálculo de avanço de mês respeitando o intervalo (Anchor Date logic)
            months_since_start = (scan_year - self.start_date.year) * 12 + (scan_month - self.start_date.month)
            months_to_advance = self.interval - (months_since_start % self.interval)

            total_months = scan_month - 1 + months_to_advance
            scan_year = scan_year + (total_months // 12)
            scan_month = (total_months % 12) + 1

        # Fallback de segurança (embora a lógica acima seja exaustiva)
        return None

    def get_next_occurrence(self, last_occurrence: Optional[datetime] = None) -> Optional[datetime]:
        """Calculates the next occurrence scanning only valid business days."""

        if last_occurrence is None:
            first = self.get_first_valid_occurrence()
            return first if not self._is_exhausted(first) else None

        last = self._normalize_comparison_date(last_occurrence)

        scan_year = last.year
        scan_month = last.month

        # Limite de segurança (2 meses)
        for _ in range(12):
            last_day_of_month = calendar.monthrange(scan_year, scan_month)[1]
            business_days_in_month: List[date] = []

            # 1. Coleta todos os dias úteis deste mês usando a função injetada
            for day_num in range(1, last_day_of_month + 1):
                d = date(scan_year, scan_month, day_num)
                if self.is_business_day(d):
                    business_days_in_month.append(d)

            # 2. Tenta aceder ao índice (positivo ou negativo)
            try:
                # Converter índice 1-based para 0-based nas listas de Python
                idx = self.nth_day - 1 if self.nth_day > 0 else self.nth_day
                target_date = business_days_in_month[idx]
                candidate = self._combine_with_start_time(target_date)

                # Se o candidato for no futuro, encontramos!
                if candidate > last:
                    if self._is_exhausted(candidate):
                        return None
                    return candidate

            except IndexError:
                # Exemplo: Pediu o 25º dia útil, mas o mês só teve 21 dias úteis.
                # Ignoramos este mês e tentamos no próximo.
                pass

            # 3. Avançar para o próximo mês válido respeitando o intervalo
            months_diff = (scan_year - self.start_date.year) * 12 + (scan_month - self.start_date.month)
            remainder = months_diff % self.interval
            months_to_advance = self.interval - remainder

            new_month = scan_month - 1 + months_to_advance
            scan_year = scan_year + (new_month // 12)
            scan_month = (new_month % 12) + 1

        return None
