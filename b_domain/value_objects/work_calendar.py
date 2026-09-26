"""What counts as a business day for a user.

Three layers, each one above the one before:

1. **Work days** of the week (the ``work_days`` preference: Monday to Friday
   unless the user says otherwise).
2. The **holidays of a region** (the ``holiday_region`` preference, e.g.
   ``BR`` or ``BR-SP``), which a ``HolidayProvider`` knows — none by default.
3. The user's **own days** (``CalendarDay``): a day off or a working day,
   once or every year. They win over the other two: a working day on a
   holiday or on a Saturday is a business day.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

from a_core import ValueObject
from a_core.exceptions import InvalidValueError, ValidationException

WEEKDAY_NAMES: tuple[str, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
"""The short names of the days of the week, Monday first (``date.weekday()``)."""

_FULL_NAMES: tuple[str, ...] = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

DEFAULT_WORK_DAYS: str = "mon,tue,wed,thu,fri"

_WORK_DAYS_HELP: str = "day names separated by commas (mon,tue,…) or a range (mon-fri)"


def weekdays_only(day: date) -> bool:
    """Monday to Friday: the business days when nothing else is known."""
    return day.weekday() < 5


def parse_work_days(text: str) -> frozenset[int]:
    """The days of the week in ``text``, as ``date.weekday()`` numbers.

    Accepts short or full English names, separated by commas or spaces, and
    ranges (``mon-fri``, ``sun-thu``: a range can wrap past Sunday).

    Raises:
        InvalidValueError: If a name is unknown or no day is given.
    """
    days: set[int] = set()
    for part in text.replace(",", " ").lower().split():
        if "-" in part:
            first, _, last = part.partition("-")
            start, end = _weekday(first, text), _weekday(last, text)
            days.update((start + i) % 7 for i in range((end - start) % 7 + 1))
        else:
            days.add(_weekday(part, text))
    if not days:
        raise InvalidValueError(
            concept="work days", invalid_value=text, valid_options=[_WORK_DAYS_HELP]
        )
    return frozenset(days)


def work_days_text(days: frozenset[int] | set[int]) -> str:
    """The canonical text of a set of days: ``mon,tue,wed,thu,fri``."""
    return ",".join(WEEKDAY_NAMES[d] for d in sorted(days))


def _weekday(name: str, text: str) -> int:
    if name in WEEKDAY_NAMES:
        return WEEKDAY_NAMES.index(name)
    if name in _FULL_NAMES:
        return _FULL_NAMES.index(name)
    raise InvalidValueError(
        concept="work days", invalid_value=text, valid_options=[_WORK_DAYS_HELP]
    )


class CalendarDayKind(StrEnum):
    """What one of the user's own days is."""

    DAY_OFF = "day_off"
    WORKDAY = "workday"


@dataclass(frozen=True, kw_only=True)
class CalendarDay(ValueObject):
    """A day the user set: a day off or a working day, once or every year.

    A user has at most one of each on a date (a one-off and a yearly one can
    share a date; the one-off wins there).

    Attributes:
        day (date): The date. For a yearly day, the first year it applies.
        kind (CalendarDayKind): A day off or a working day.
        yearly (bool): Repeats every year on the same month and day (from
            ``day``'s year on). A yearly 29 February only falls on leap years.
        name (str): What the day is ("Company recess"); may be empty.
    """

    NAME_MAX_LENGTH = 100

    day: date
    kind: CalendarDayKind
    yearly: bool = False
    name: str = ""

    def __post_init__(self) -> None:
        name: str = " ".join(self.name.split())
        if len(name) > self.NAME_MAX_LENGTH:
            raise ValidationException(
                f"A day's name takes up to {self.NAME_MAX_LENGTH} characters."
            )
        object.__setattr__(self, "name", name)

    @property
    def is_day_off(self) -> bool:
        """A day off (else, a working day)."""
        return self.kind is CalendarDayKind.DAY_OFF

    def applies_to(self, day: date) -> bool:
        """Whether this day falls on ``day``."""
        if not self.yearly:
            return day == self.day
        return (day.month, day.day) == (self.day.month, self.day.day) and (
            day.year >= self.day.year
        )


@dataclass(frozen=True)
class HolidayRegion(ValueObject):
    """A region whose holidays are known: ``BR`` Brazil, ``BR-SP`` São Paulo.

    Attributes:
        code (str): The country's ISO 3166 code, or the country and one of
            its subdivisions (``BR-SP``).
        name (str): Its name (a country's in English; a subdivision's as the
            holidays provider has it).
    """

    code: str
    name: str

    @property
    def is_country(self) -> bool:
        """A whole country (no subdivision)."""
        return "-" not in self.code


type HolidayLookup = Callable[[int], Mapping[date, str]]
"""A year → that year's holidays (date → name) in the user's region."""


def no_holidays(year: int) -> Mapping[date, str]:
    """No region set: no holidays."""
    return {}


@dataclass(frozen=True, kw_only=True)
class WorkCalendar:
    """The user's business days: work days, a region's holidays, own days.

    Attributes:
        work_days (frozenset[int]): The days of the week the user works
            (``date.weekday()``: 0 = Monday).
        region (str): The holiday region (``BR``, ``BR-SP``), or empty.
        holidays (HolidayLookup): The region's holidays for a year.
        days (tuple[CalendarDay, ...]): The user's own days.
    """

    work_days: frozenset[int] = frozenset(range(5))
    region: str = ""
    holidays: HolidayLookup = field(default=no_holidays, compare=False, repr=False)
    days: tuple[CalendarDay, ...] = ()
    _by_year: dict[int, Mapping[date, str]] = field(
        default_factory=dict, compare=False, repr=False
    )

    def is_business_day(self, day: date) -> bool:
        """Whether the user works on ``day``.

        Their own day decides first; else it is a work day of the week that
        is not a holiday of their region.
        """
        own: CalendarDay | None = self.own_day(day)
        if own is not None:
            return not own.is_day_off
        return day.weekday() in self.work_days and self.holiday(day) is None

    def own_day(self, day: date) -> CalendarDay | None:
        """The user's own day on ``day``: the one-off first, then a yearly one."""
        matches: list[CalendarDay] = [d for d in self.days if d.applies_to(day)]
        matches.sort(key=lambda d: d.yearly)
        return matches[0] if matches else None

    def holiday(self, day: date) -> str | None:
        """The name of the region's holiday on ``day``, if there is one."""
        if day.year not in self._by_year:
            self._by_year[day.year] = self.holidays(day.year)
        return self._by_year[day.year].get(day)
