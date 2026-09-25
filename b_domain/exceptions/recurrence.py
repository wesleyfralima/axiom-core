from datetime import datetime
from typing import Any

from a_core import DomainException


class RecurrenceRuleException(DomainException):
    """Base exception for recurrence rule violations."""

    def __init__(self, message: str = "Invalid recurrence rule configuration."):
        super().__init__(message)


class MutuallyExclusiveEndDateAndCount(RecurrenceRuleException):
    """Raised when both `end_date` and `count` are provided."""

    def __init__(self) -> None:
        super().__init__(
            "Cannot define both 'end_date' and 'count' for a recurrence rule. "
            "They are mutually exclusive."
        )


class InvalidIntervalValue(RecurrenceRuleException):
    """Raised when the recurrence interval value is invalid."""

    def __init__(self, invalid_value: Any) -> None:
        self.invalid_value = invalid_value
        super().__init__(
            f"Invalid recurrence interval: '{invalid_value}'. "
            f"It must be an integer greater than or equal to 1."
        )


class EndDateBeforeStartDate(RecurrenceRuleException):
    """Raised when `end_date` is earlier than `start_date`."""

    def __init__(self, start_date: datetime, end_date: datetime) -> None:
        self.start_date = start_date
        self.end_date = end_date
        # Formata a data para uma leitura mais limpa (opcional)
        start_str = start_date.strftime("%Y-%m-%d %H:%M")
        end_str = end_date.strftime("%Y-%m-%d %H:%M")
        super().__init__(
            f"The end date ({end_str}) cannot be "
            f"earlier than the start date ({start_str})."
        )


class MutuallyExclusiveWeekAndMonthDays(RecurrenceRuleException):
    """Raised when both `by_week_days` and `by_month_days` are defined."""

    def __init__(self) -> None:
        super().__init__(
            "Cannot define both 'by_week_days' and 'by_month_days'. "
            "These rules cannot be combined."
        )


class BySetPosWithoutDaySet(RecurrenceRuleException):
    """Raised when `by_set_pos` is defined without `by_week_days` or `by_month_days`."""

    def __init__(self) -> None:
        super().__init__(
            "The 'by_set_pos' rule requires either 'by_week_days' "
            "or 'by_month_days' to operate correctly."
        )


class NthBusinessDayRequiresPredicate(RecurrenceRuleException):
    """Raised when `nth_business_day` is defined without a business-day predicate."""

    def __init__(self) -> None:
        super().__init__(
            "A callable function ('is_business_day') must "
            "be provided to evaluate 'nth_business_day'."
        )


class NthBusinessDayWithOtherDayRules(RecurrenceRuleException):
    """Raised when `nth_business_day` is combined with other day-based rules."""

    def __init__(self) -> None:
        super().__init__(
            "Business-day rules ('nth_business_day') cannot "
            "be mixed with 'by_week_days' or 'by_month_days'."
        )


class InvalidWeekDayValue(RecurrenceRuleException):
    """Raised when an invalid weekday value is provided."""

    def __init__(self, invalid_day: Any) -> None:
        self.invalid_day = invalid_day
        super().__init__(
            f"Invalid weekday value: '{invalid_day}'. "
            f"Valid values are integers from 0 (Monday) to 6 (Sunday)."
        )


class InvalidMonthDayValue(RecurrenceRuleException):
    """Raised when an invalid month day value is provided."""

    def __init__(self, invalid_day: Any) -> None:
        self.invalid_day = invalid_day
        super().__init__(
            f"Invalid month day value: '{invalid_day}'. "
            f"Valid values range from 1 to 31."
        )


class BySetPosWithMonthDays(RecurrenceRuleException):
    """Raised when BySetPos is used together with month days."""

    def __init__(self) -> None:
        super().__init__(
            "The 'by_set_pos' rule cannot be used together with 'by_month_days'."
        )


class BySetPosRequiresMonthlyFrequency(RecurrenceRuleException):
    """Raised when BySetPos is used without a monthly frequency."""

    def __init__(self, current_frequency: str) -> None:
        self.current_frequency = current_frequency
        super().__init__(
            f"The 'by_set_pos' rule requires a 'MONTHLY' frequency, "
            f"but '{current_frequency}' was provided."
        )
