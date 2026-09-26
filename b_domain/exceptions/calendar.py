from a_core.exceptions import DomainException, InvalidValueError
from b_domain.value_objects.work_calendar import HolidayRegion


class UnknownHolidayRegionError(InvalidValueError):
    """Raised when no holidays are known for a region; suggests close ones."""

    def __init__(self, region: str, suggestions: list[HolidayRegion] | None = None):
        self.region = region
        self.suggestions: list[HolidayRegion] = suggestions or []
        message: str = f"No holidays known for the region '{region}'."
        if self.suggestions:
            names: str = ", ".join(f"{r.code} ({r.name})" for r in self.suggestions)
            message += f" Did you mean {names}?"
        DomainException.__init__(self, message)
