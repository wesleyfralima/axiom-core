from dataclasses import dataclass
from datetime import datetime, time

from a_core import DTO
from b_domain.value_objects.enums import RecurrenceInterval
from c_application.utils.date_input import DateInput


@dataclass(frozen=True, kw_only=True)
class RecurrenceInputDTO(DTO):
    """Data Transfer Object for recurrence rules.

    This DTO represents recurrence configuration for tasks or events.
    It serves as a bridge between the presentation layer (API) and the
    Domain's RecurrenceFactory, using primitive types for easy serialization.
    """

    # Core recurrence definition
    frequency: RecurrenceInterval
    # The first date (a DateInput; a date alone gets the user's default due
    # time). None: today, at the default due time
    start_date: DateInput | None = None
    catch_up: bool = True
    interval: int = 1

    # End conditions
    # A date alone means the end of that day
    end_date: DateInput | None = None
    count: int | None = None

    # Day-based rules
    # Lists are used instead of Sets because JSON arrays naturally map to Lists.
    # The Use Case/Factory will convert these to Sets for the Domain.
    by_week_days: list[int] | None = None  # e.g., [0, 2] for Monday, Wednesday
    by_month_days: list[int] | None = None  # e.g., [1, 15] for 1st and 15th
    by_set_pos: int | None = None  # e.g., 1 for "first occurrence"

    # Business day rules
    nth_business_day: int | None = None  # e.g., 3 for "third business day"

    # Hourly window rules
    window_start: time | None = None
    window_end: time | None = None


@dataclass(frozen=True, kw_only=True)
class RecurrenceOutputDTO(DTO):
    """A task's rule in the terms it was created with (``RecurrenceInputDTO``).

    Lets an interface show the rule as editable fields and send it back.
    ``count`` is how many occurrences are left, the current one included.
    """

    frequency: RecurrenceInterval
    interval: int = 1
    end_date: datetime | None = None
    count: int | None = None
    by_week_days: list[int] | None = None
    by_month_days: list[int] | None = None
    by_set_pos: int | None = None
    nth_business_day: int | None = None
    window_start: time | None = None
    window_end: time | None = None
