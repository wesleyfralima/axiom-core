from datetime import date, datetime, time
from typing import Callable, Optional, Set

from a_core import ValidationException
from b_domain.value_objects.enums import RecurrenceInterval
from b_domain.value_objects.recurrences import RecurrenceRule
from b_domain.value_objects.recurrences.by_business_days import BusinessDayRule
from b_domain.value_objects.recurrences.hourly import HourlyWindowRule
from b_domain.value_objects.recurrences.monthly_by_days import MonthlyByDaysRule
from b_domain.value_objects.recurrences.monthly_by_position import MonthlyPositionalRule
from b_domain.value_objects.recurrences.monthly_by_weekday_pos import MonthlyWeekdayPositionalRule
from b_domain.value_objects.recurrences.monthly_by_weekdays import MonthlyAllWeekdaysRule
from b_domain.value_objects.recurrences.simple import SimpleIntervalRule
from b_domain.value_objects.recurrences.weekly_by_days import WeeklyByDaysRule


class RecurrenceFactory:
    """Domain Factory for instantiating the correct RecurrenceRule strategy."""

    @staticmethod
    def create_from_input(
            start_date: datetime,
            frequency: RecurrenceInterval,
            interval: int = 1,
            end_date: Optional[datetime] = None,
            count: Optional[int] = None,
            days_of_week: Optional[Set[int]] = None,
            days_of_month: Optional[Set[int]] = None,
            set_pos: Optional[int] = None,
            nth_business_day: Optional[int] = None,
            is_business_day_checker: Optional[Callable[[date], bool]] = None,
            window_start: Optional[time] = None,
            window_end: Optional[time] = None,
    ) -> RecurrenceRule:
        """
        Analyzes the provided parameters and returns the appropriate polymorphic
        RecurrenceRule object.
        """

        # 1. Regra de Dias Úteis (Business Days)
        if nth_business_day is not None:
            if not is_business_day_checker:
                raise ValidationException("is_business_day_checker is required for business day rules.")
            return BusinessDayRule(
                start_date=start_date,
                interval=interval,
                end_date=end_date,
                count=count,
                nth_day=nth_business_day,
                is_business_day=is_business_day_checker,
            )

        # 2. Regra por Hora com Janela (Hourly Window)
        if frequency == RecurrenceInterval.HOURLY and window_start and window_end:
            return HourlyWindowRule(
                start_date=start_date,
                interval=interval,
                end_date=end_date,
                count=count,
                window_start=window_start,
                window_end=window_end,
            )

        # 3. Regras Semanais
        if frequency == RecurrenceInterval.WEEKLY:
            if days_of_week:
                return WeeklyByDaysRule(
                    start_date=start_date,
                    interval=interval,
                    end_date=end_date,
                    count=count,
                    days_of_week=days_of_week,
                )

        # 4. Regras Mensais
        if frequency == RecurrenceInterval.MONTHLY:

            # Ex: Dia 5 e 20
            if days_of_month:
                return MonthlyByDaysRule(
                    start_date=start_date,
                    interval=interval,
                    end_date=end_date,
                    count=count,
                    days_of_month=days_of_month,
                )

            # Ex: Último dia do mês (-1)
            if set_pos is not None and not days_of_week:
                return MonthlyPositionalRule(
                    start_date=start_date,
                    interval=interval,
                    end_date=end_date,
                    count=count,
                    set_pos=set_pos,
                )

            # Ex: Todas as sextas-feiras do mês
            if days_of_week and set_pos is None:
                return MonthlyAllWeekdaysRule(
                    start_date=start_date,
                    interval=interval,
                    end_date=end_date,
                    count=count,
                    days_of_week=days_of_week,
                )

            # Ex: A segunda sexta-feira do mês
            if days_of_week and set_pos is not None:
                return MonthlyWeekdayPositionalRule(
                    start_date=start_date,
                    interval=interval,
                    end_date=end_date,
                    count=count,
                    days_of_week=days_of_week,
                    set_pos=set_pos,
                )

        # 5. Fallback: Regra de Intervalo Simples
        # (HOURLY sem janela, DAILY, YEARLY ou WEEKLY/MONTHLY simples sem dias específicos)
        return SimpleIntervalRule(
            start_date=start_date,
            interval=interval,
            end_date=end_date,
            count=count,
            frequency=frequency,
        )
