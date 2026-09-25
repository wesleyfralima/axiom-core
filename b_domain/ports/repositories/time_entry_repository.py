from abc import ABC, abstractmethod

from b_domain.entities.time_entry import TimeEntry
from b_domain.ports.repositories.filters import TimeEntryFilter
from b_domain.value_objects.identifiers import TaskId, TimeEntryId, UserId


class TimeEntryRepository(ABC):
    """
    Port (Interface) for persisting and retrieving time tracking data.
    """

    @abstractmethod
    async def add(self, entry: TimeEntry) -> TimeEntry:
        """Persists a new time entry."""
        raise NotImplementedError

    @abstractmethod
    async def update(self, entry: TimeEntry) -> None:
        """Updates an existing time entry (e.g., when stopping a timer)."""
        raise NotImplementedError

    @abstractmethod
    async def update_all(self, entries: list[TimeEntry]) -> None:
        """Batch update for multiple entries."""
        raise NotImplementedError

    @abstractmethod
    async def get_by_id(self, entry_id: TimeEntryId) -> TimeEntry | None:
        """Retrieves a specific entry by its unique ID."""
        raise NotImplementedError

    @abstractmethod
    async def get_actives_for_task(self, task_id: TaskId) -> list[TimeEntry]:
        """
        Finds all running timers (where end_time is None) for a specific task.
        Used by CompleteTaskUseCase to ensure no timers stay open.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_active_for_user(self, user_id: UserId) -> TimeEntry | None:
        """
        Finds the currently running timer for a user.
        Useful to enforce the business rule: 'One timer at a time'.
        """
        raise NotImplementedError

    @abstractmethod
    async def find_by_user(self, user_id: UserId) -> list[TimeEntry]:
        """Retrieves the full time tracking history for a user."""
        raise NotImplementedError

    @abstractmethod
    async def search(self, filters: TimeEntryFilter) -> list[TimeEntry]:
        """Searches for time entries matching the given filters."""
        raise NotImplementedError
