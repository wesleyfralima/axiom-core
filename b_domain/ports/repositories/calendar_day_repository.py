from abc import ABC, abstractmethod
from datetime import date

from b_domain.value_objects.identifiers import UserId
from b_domain.value_objects.work_calendar import CalendarDay


class CalendarDayRepository(ABC):
    """The user's own days: days off and working days, once or yearly.

    A day is known by its user, date and ``yearly``: saving another one with
    the same three replaces it. Days are values, not entities (they record no
    events), so this is not a ``BaseRepository``.
    """

    @abstractmethod
    async def list_by_user(self, user_id: UserId) -> list[CalendarDay]:
        """All of the user's days, by date.

        Args:
            user_id (UserId): The owner.

        Returns:
            list[CalendarDay]: The days.
        """

    @abstractmethod
    async def save(self, user_id: UserId, day: CalendarDay) -> None:
        """Add a day, or replace the one with the same date and ``yearly``.

        Args:
            user_id (UserId): The owner.
            day (CalendarDay): The day.
        """

    @abstractmethod
    async def remove(self, user_id: UserId, day: date, yearly: bool) -> None:
        """Remove the day with this date and ``yearly`` (nothing if none).

        Args:
            user_id (UserId): The owner.
            day (date): The day's date, as saved.
            yearly (bool): Which of the two kinds.
        """
