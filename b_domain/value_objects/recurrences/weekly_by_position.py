from dataclasses import dataclass, field
from datetime import datetime

from a_core.exceptions import ValidationException
from a_core.text import ordinal_phrase
from b_domain.value_objects.recurrences import RecurrenceRule
from b_domain.value_objects.recurrences._base import WEEKDAY_NAMES
from b_domain.value_objects.recurrences.weekly_by_days import WeeklyByDaysRule

_DAY_CODES: tuple[str, ...] = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")


@dataclass(frozen=True, kw_only=True)
class WeeklyPositionalRule(RecurrenceRule):
    """Rule for the N-th day of the week, the weekly twin of
    ``MonthlyPositionalRule``.

    Handles recurrences like "The last day of the week" (set_pos = -1) or
    "The second day of the week" (set_pos = 2). Days are counted from the
    week's first day, which is the user's choice (Monday or Sunday), so the
    position always lands on the same weekday: that is the one repeated.

    Attributes:
        set_pos (int): 1 to 7 from the start of the week, -1 to -7 from the
            end (-1 = last day). Cannot be 0.
        week_start (int): The week's first day (0 = Monday … 6 = Sunday).
    """

    set_pos: int
    week_start: int = 0

    _weekly: WeeklyByDaysRule = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Validate the position and resolve the weekday it lands on.

        Raises:
            ValidationException: If `set_pos` is 0 or outside -7 to 7, or
                `week_start` is not a weekday (0-6).
        """
        super().__post_init__()
        object.__setattr__(self, "_freq", "WEEKLY")

        if self.set_pos == 0 or not -7 <= self.set_pos <= 7:
            raise ValidationException(
                "The day of the week (set_pos) must be 1 to 7 or -1 to -7."
            )
        if not 0 <= self.week_start <= 6:
            raise ValidationException("week_start must be a weekday (0-6).")

        object.__setattr__(
            self,
            "_weekly",
            WeeklyByDaysRule(
                start_date=self.start_date,
                interval=self.interval,
                end_date=self.end_date,
                count=self.count,
                days_of_week={self.weekday},
            ),
        )

    @property
    def weekday(self) -> int:
        """The weekday the position lands on (0 = Monday … 6 = Sunday)."""
        offset: int = self.set_pos - 1 if self.set_pos > 0 else 7 + self.set_pos
        return (self.week_start + offset) % 7

    def _rrule_extra_parts(self) -> list[str]:
        """BYDAY with every day, BYSETPOS and the week's first day (RFC 5545)."""
        return [
            f"BYDAY={','.join(_DAY_CODES)}",
            f"BYSETPOS={self.set_pos}",
            f"WKST={_DAY_CODES[self.week_start]}",
        ]

    def describe_pattern(self) -> str:
        """Describe the rule: "Every week on the last day (Sunday)"."""
        position: str = ordinal_phrase(self.set_pos)
        return (
            f"{self._every('week')} on the {position} day "
            f"({WEEKDAY_NAMES[self.weekday]})"
        )

    def get_first_valid_occurrence(self) -> datetime:
        """The first occurrence on or after start_date."""
        return self._weekly.get_first_valid_occurrence()

    def get_next_occurrence(
        self, last_occurrence: datetime | None = None
    ) -> datetime | None:
        """The occurrence after ``last_occurrence`` (the weekday it lands on)."""
        return self._weekly.get_next_occurrence(last_occurrence)
