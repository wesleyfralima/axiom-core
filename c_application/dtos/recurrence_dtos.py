from dataclasses import dataclass
from datetime import datetime, time
from typing import List, Optional

from a_core import DTO
from b_domain.value_objects.enums import RecurrenceInterval


@dataclass(frozen=True, kw_only=True)
class RecurrenceInputDTO(DTO):
    """Data Transfer Object for recurrence rules.

    This DTO represents recurrence configuration for tasks or events.
    It serves as a bridge between the presentation layer (API) and the
    Domain's RecurrenceFactory, using primitive types for easy serialization.
    """

    # Core recurrence definition
    frequency: RecurrenceInterval
    start_date: datetime
    catch_up: bool = True
    interval: int = 1

    # End conditions
    end_date: Optional[datetime] = None
    count: Optional[int] = None

    # Day-based rules
    # Lists are used instead of Sets because JSON arrays naturally map to Lists.
    # The Use Case/Factory will convert these to Sets for the Domain.
    by_week_days: Optional[List[int]] = None   # e.g., [0, 2] for Monday, Wednesday
    by_month_days: Optional[List[int]] = None  # e.g., [1, 15] for 1st and 15th
    by_set_pos: Optional[int] = None           # e.g., 1 for "first occurrence"

    # Business day rules
    nth_business_day: Optional[int] = None     # e.g., 3 for "third business day"

    # Hourly window rules
    window_start: Optional[time] = None
    window_end: Optional[time] = None
