from typing import Any

from b_domain.value_objects.enums import RecurrenceInterval
from b_domain.value_objects.recurrences import RecurrenceRule
from c_application.dtos.recurrence_dtos import RecurrenceOutputDTO


class RecurrenceMapper:
    """Rule → the fields it would be created from (the factory in reverse)."""

    @staticmethod
    def to_output(rule: RecurrenceRule) -> RecurrenceOutputDTO:
        """Read a rule back as ``RecurrenceOutputDTO``.

        Each rule class keeps only its own fields; the others stay None.
        """
        simple_frequency: Any = getattr(rule, "frequency", None)
        days_of_week: set[int] | None = getattr(rule, "days_of_week", None)
        days_of_month: set[int] | None = getattr(rule, "days_of_month", None)
        return RecurrenceOutputDTO(
            frequency=(
                simple_frequency
                if isinstance(simple_frequency, RecurrenceInterval)
                else RecurrenceInterval[rule._freq]
            ),
            interval=rule.interval,
            end_date=rule.end_date.value if rule.end_date else None,
            count=rule.count,
            by_week_days=sorted(days_of_week) if days_of_week else None,
            by_month_days=sorted(days_of_month) if days_of_month else None,
            by_set_pos=getattr(rule, "set_pos", None),
            nth_business_day=getattr(rule, "nth_day", None),
            window_start=getattr(rule, "window_start", None),
            window_end=getattr(rule, "window_end", None),
            keep_missed=rule.keep_missed,
        )
