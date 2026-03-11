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
    Domain's RecurrenceFactory.
    """

    frequency: RecurrenceInterval
    start_date: datetime

    interval: int = 1

    end_date: Optional[datetime] = None
    count: Optional[int] = None

    # List is used instead of Set because JSON arrays parse naturally to Lists.
    # The Use Case/Factory will convert these to Sets for the Domain.
    by_week_days: Optional[List[int]] = None
    by_month_days: Optional[List[int]] = None
    by_set_pos: Optional[int] = None

    nth_business_day: Optional[int] = None

    # New fields to support the HourlyWindowRule
    window_start: Optional[time] = None
    window_end: Optional[time] = None
