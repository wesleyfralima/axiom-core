from collections.abc import Callable
from datetime import date, time

from b_domain.exceptions.recurrence import (
    BySetPosRequiresWeeklyOrMonthly,
    BySetPosWithMonthDays,
    BySetPosWithWeekdaysInAWeek,
)
from b_domain.value_objects.dates import AxiomDate
from b_domain.value_objects.enums import RecurrenceInterval
from b_domain.value_objects.recurrences import RecurrenceRule
from b_domain.value_objects.recurrences.by_business_days import BusinessDayRule
from b_domain.value_objects.recurrences.hourly import HourlyWindowRule
from b_domain.value_objects.recurrences.monthly_by_days import MonthlyByDaysRule
from b_domain.value_objects.recurrences.monthly_by_position import (
    MonthlyPositionalRule,
)
from b_domain.value_objects.recurrences.monthly_by_weekday_pos import (
    MonthlyWeekdayPositionalRule,
)
from b_domain.value_objects.recurrences.monthly_by_weekdays import (
    MonthlyAllWeekdaysRule,
)
from b_domain.value_objects.recurrences.simple import SimpleIntervalRule
from b_domain.value_objects.recurrences.weekly_by_days import WeeklyByDaysRule
from b_domain.value_objects.recurrences.weekly_by_position import (
    WeeklyPositionalRule,
)
from b_domain.value_objects.work_calendar import weekdays_only


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
        end_date: AxiomDate | None = None,
        count: int | None = None,
        days_of_week: set[int] | None = None,
        days_of_month: set[int] | None = None,
        set_pos: int | None = None,
        nth_business_day: int | None = None,
        is_business_day_checker: Callable[[date], bool] | None = None,
        window_start: time | None = None,
        window_end: time | None = None,
        week_start: int = 0,
    ) -> RecurrenceRule:
        """Create the appropriate recurrence rule based on input parameters.

        Args:
            start_date (AxiomDate): The date when recurrence starts.
            frequency (RecurrenceInterval): The recurrence frequency
                (HOURLY, DAILY, WEEKLY, MONTHLY, YEARLY).
            interval (int, optional): Interval between occurrences. Defaults to 1.
            end_date (Optional[AxiomDate], optional): End date for recurrence.
                Defaults to None.
            count (Optional[int], optional): Maximum number of occurrences.
                Defaults to None.
            days_of_week (Optional[Set[int]], optional): Specific weekdays for
                recurrence (0=Monday, 6=Sunday). Defaults to None.
            days_of_month (Optional[Set[int]], optional): Specific days of the
                month for recurrence. Defaults to None.
            set_pos (Optional[int], optional): Positional indicator
                (e.g., last day of month = -1). Defaults to None.
            nth_business_day (Optional[int], optional): Nth business day of the
                month. Defaults to None.
            is_business_day_checker (Optional[Callable[[date], bool]], optional):
                Whether a date is a business day (the user's calendar).
                Defaults to Monday to Friday.
            window_start (Optional[time], optional): Start time for hourly
                window rules. Defaults to None.
            window_end (Optional[time], optional): End time for hourly
                window rules. Defaults to None.
            week_start (int, optional): The week's first day (0 = Monday,
                6 = Sunday), for "the Nth day of the week". Defaults to 0.

        Returns:
            RecurrenceRule: The appropriate recurrence rule implementation.

        Raises:
            ValidationException: If required parameters are missing or invalid.
            RecurrenceRuleException: If a position (``set_pos``) is given to a
                rule that is neither weekly nor monthly, together with days of
                the month, or to a weekly rule together with weekdays.
        """
        # 0. A position is the Nth day of a week or of a month: never ignored
        if set_pos is not None and nth_business_day is None:
            if frequency not in (RecurrenceInterval.WEEKLY, RecurrenceInterval.MONTHLY):
                raise BySetPosRequiresWeeklyOrMonthly(frequency.name.lower())
            if days_of_month:
                raise BySetPosWithMonthDays()
            if frequency == RecurrenceInterval.WEEKLY and days_of_week:
                raise BySetPosWithWeekdaysInAWeek()

        # 1. Business Day Rule
        if nth_business_day is not None:
            return BusinessDayRule(
                start_date=start_date,
                interval=interval,
                end_date=end_date,
                count=count,
                nth_day=nth_business_day,
                is_business_day=is_business_day_checker or weekdays_only,
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
            # Ex: The last day of the week
            if set_pos is not None:
                return WeeklyPositionalRule(
                    start_date=start_date,
                    interval=interval,
                    end_date=end_date,
                    count=count,
                    set_pos=set_pos,
                    week_start=week_start,
                )
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

            # Ex: Every Friday of the month
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
