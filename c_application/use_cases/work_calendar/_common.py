from datetime import date

from b_domain.value_objects.work_calendar import CalendarDay, WorkCalendar
from c_application.dtos.calendar_dtos import CalendarDayOutputDTO


def next_date(day: CalendarDay, today: date) -> date:
    """The next date ``day`` falls on, today included (a yearly one repeats)."""
    if not day.yearly or day.day >= today:
        return day.day
    for year in range(today.year, today.year + 9):
        try:
            candidate: date = day.day.replace(year=year)
        except ValueError:  # 29 February, not a leap year
            continue
        if candidate >= today:
            return candidate
    return day.day


def own_day_output(
    day: CalendarDay, on: date, calendar: WorkCalendar
) -> CalendarDayOutputDTO:
    """One of the user's days, as it falls on ``on``."""
    holiday: str | None = calendar.holiday(on)
    return CalendarDayOutputDTO(
        date=on.isoformat(),
        name=day.name or holiday or "",
        source="yours",
        is_business_day=not day.is_day_off,
        kind=day.kind.value,
        yearly=day.yearly,
        holiday=holiday,
    )
