from datetime import date, time
from typing import Callable, Optional, Set

from a_core import ValidationException
from b_domain.value_objects.dates import AxiomDate
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
    """Domain factory for instantiating the correct RecurrenceRule strategy.

    This factory analyzes the provided parameters and selects the
    appropriate recurrence rule implementation (e.g., business days,
    hourly windows, weekly, monthly, or simple interval rules).
    """

    @staticmethod
    def create_from_input(
            start_date: AxiomDate,
            frequency: RecurrenceInterval,
            interval: int = 1,
            end_date: Optional[AxiomDate] = None,
            count: Optional[int] = None,
            days_of_week: Optional[Set[int]] = None,
            days_of_month: Optional[Set[int]] = None,
            set_pos: Optional[int] = None,
            nth_business_day: Optional[int] = None,
            is_business_day_checker: Optional[Callable[[date], bool]] = None,
            window_start: Optional[time] = None,
            window_end: Optional[time] = None,
    ) -> RecurrenceRule:
        """Create the appropriate recurrence rule based on input parameters.

        Args:
            start_date (AxiomDate): The date when recurrence starts.
            frequency (RecurrenceInterval): The recurrence frequency (HOURLY, DAILY, WEEKLY, MONTHLY, YEARLY).
            interval (int, optional): Interval between occurrences. Defaults to 1.
            end_date (Optional[AxiomDate], optional): End date for recurrence. Defaults to None.
            count (Optional[int], optional): Maximum number of occurrences. Defaults to None.
            days_of_week (Optional[Set[int]], optional): Specific weekdays for recurrence (0=Monday, 6=Sunday). Defaults to None.
            days_of_month (Optional[Set[int]], optional): Specific days of the month for recurrence. Defaults to None.
            set_pos (Optional[int], optional): Positional indicator (e.g., last day of month = -1). Defaults to None.
            nth_business_day (Optional[int], optional): Nth business day of the month. Defaults to None.
            is_business_day_checker (Optional[Callable[[date], bool]], optional): Function to check if a date is a business day. Required if `nth_business_day` is set.
            window_start (Optional[time], optional): Start time for hourly window rules. Defaults to None.
            window_end (Optional[time], optional): End time for hourly window rules. Defaults to None.

        Returns:
            RecurrenceRule: The appropriate recurrence rule implementation.

        Raises:
            ValidationException: If required parameters are missing or invalid.
        """
        # 1. Business Day Rule
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

        # 2. Hourly Window Rule
        if frequency == RecurrenceInterval.HOURLY and window_start and window_end:
            return HourlyWindowRule(
                start_date=start_date,
                interval=interval,
                end_date=end_date,
                count=count,
                window_start=window_start,
                window_end=window_end,
            )

        # 3. Weekly Rules
        if frequency == RecurrenceInterval.WEEKLY:
            if days_of_week:
                return WeeklyByDaysRule(
                    start_date=start_date,
                    interval=interval,
                    end_date=end_date,
                    count=count,
                    days_of_week=days_of_week,
                )

        # 4. Monthly Rules
        if frequency == RecurrenceInterval.MONTHLY:

            # Ex: Days 5 and 20
            if days_of_month:
                return MonthlyByDaysRule(
                    start_date=start_date,
                    interval=interval,
                    end_date=end_date,
                    count=count,
                    days_of_month=days_of_month,
                )

            # Ex: Last day of the month
            if set_pos is not None and not days_of_week:
                return MonthlyPositionalRule(
                    start_date=start_date,
                    interval=interval,
                    end_date=end_date,
                    count=count,
                    set_pos=set_pos,
                )

            # Ex: Every fridays of the month
            if days_of_week and set_pos is None:
                return MonthlyAllWeekdaysRule(
                    start_date=start_date,
                    interval=interval,
                    end_date=end_date,
                    count=count,
                    days_of_week=days_of_week,
                )

            # Ex: The second monday of the month
            if days_of_week and set_pos is not None:
                return MonthlyWeekdayPositionalRule(
                    start_date=start_date,
                    interval=interval,
                    end_date=end_date,
                    count=count,
                    days_of_week=days_of_week,
                    set_pos=set_pos,
                )

        # 5. Fallback: Simple Interval Rule
        # - HOURLY without window
        # - DAILY, WEEKLY, MONTHLY, YEARLY without any specific behavior
        return SimpleIntervalRule(
            start_date=start_date,
            interval=interval,
            end_date=end_date,
            count=count,
            frequency=frequency,
        )
