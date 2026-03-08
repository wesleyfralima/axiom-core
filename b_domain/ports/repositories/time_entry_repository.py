from abc import ABC, abstractmethod
from typing import List, Optional

from b_domain.entities.time_entry import TimeEntry
from b_domain.value_objects.identifiers import TaskId, UserId, TimeEntryId


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
    async def update_all(self, entries: List[TimeEntry]) -> None:
        """Batch update for multiple entries."""
        raise NotImplementedError

    @abstractmethod
    async def get_by_id(self, entry_id: TimeEntryId) -> Optional[TimeEntry]:
        """Retrieves a specific entry by its unique ID."""
        raise NotImplementedError

    @abstractmethod
    async def get_actives_for_task(self, task_id: TaskId) -> List[TimeEntry]:
        """
        Finds all running timers (where end_time is None) for a specific task.
        Used by CompleteTaskUseCase to ensure no timers stay open.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_active_for_user(self, user_id: UserId) -> Optional[TimeEntry]:
        """
        Finds the currently running timer for a user.
        Useful to enforce the business rule: 'One timer at a time'.
        """
        raise NotImplementedError

    @abstractmethod
    async def find_by_user(self, user_id: UserId) -> List[TimeEntry]:
        """Retrieves the full time tracking history for a user."""
        raise NotImplementedError
