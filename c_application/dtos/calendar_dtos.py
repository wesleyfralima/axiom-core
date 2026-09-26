from dataclasses import dataclass, field

from a_core import DTO


@dataclass(frozen=True, kw_only=True)
class CalendarDayOutputDTO(DTO):
    """A day that is not like the others: a holiday or one of the user's own.

    Attributes:
        date (str): The date (ISO, ``2026-12-25``).
        name (str): What the day is (the holiday's name, or the user's own
            name for it; may be empty for an own day).
        source (str): ``holiday`` (the region's) or ``yours``.
        is_business_day (bool): Whether the user works that day, everything
            considered.
        kind (str | None): For one of the user's days, ``day_off`` or
            ``workday``; None for a holiday.
        yearly (bool): One of the user's days that repeats every year.
        holiday (str | None): The region's holiday on that date, when one of
            the user's days falls on it (and decides over it).
    """

    date: str
    name: str
    source: str
    is_business_day: bool
    kind: str | None = None
    yearly: bool = False
    holiday: str | None = None


@dataclass(frozen=True, kw_only=True)
class WorkCalendarOutputDTO(DTO):
    """What a business day is for the user, and the special days ahead.

    Attributes:
        work_days (str): The days of the week they work (``mon,tue,…``).
        holiday_region (str): Whose holidays count (``BR-SP``), or empty.
        suggested_region (str | None): With no region set, the one their time
            zone points to (for them to confirm), if any.
        start (str): The first day looked at (ISO): the user's today.
        until (str): The last day looked at (ISO).
        days (list[CalendarDayOutputDTO]): The holidays and own days in that
            window, by date.
    """

    work_days: str
    holiday_region: str
    start: str
    until: str
    suggested_region: str | None = None
    days: list[CalendarDayOutputDTO] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class CalendarDayChangedOutputDTO(DTO):
    """One of the user's days, just set or removed.

    Attributes:
        action (str): ``added``, ``replaced`` (it had the other kind, or
            another name) or ``removed``.
        day (CalendarDayOutputDTO): The day, on the next date it falls (for a
            removed day, what it was).
        changes_nothing (bool): Set, but that date was already what the day
            says (a day off on a Sunday, a working day on a Tuesday).
    """

    action: str
    day: CalendarDayOutputDTO
    changes_nothing: bool = False


@dataclass(frozen=True, kw_only=True)
class HolidayRegionOutputDTO(DTO):
    """A region whose holidays are known.

    Attributes:
        code (str): What ``holiday_region`` takes: ``BR``, ``BR-SP``.
        name (str): Its name: "Brazil", "São Paulo".
    """

    code: str
    name: str


@dataclass(frozen=True, kw_only=True)
class HolidayRegionsOutputDTO(DTO):
    """The regions to choose from: every country, a search, or a country's
    subdivisions.

    Attributes:
        query (str | None): What was searched (None: every country).
        country (HolidayRegionOutputDTO | None): When the query is a
            country's code, that country (its subdivisions follow).
        regions (list[HolidayRegionOutputDTO]): The countries or
            subdivisions found, best match first (a country's, by code).
        current_region (str): The user's region now ("" when none).
    """

    query: str | None
    regions: list[HolidayRegionOutputDTO] = field(default_factory=list)
    country: HolidayRegionOutputDTO | None = None
    current_region: str = ""
