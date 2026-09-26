from abc import ABC, abstractmethod

from b_domain.value_objects.identifiers import TaskId, UserId
from b_domain.value_objects.task_history import TaskHistoryEntry


class TaskHistoryRepository(ABC):
    """Append-only store of what happened to each task.

    Written by the unit of work, in the same transaction as the change;
    never updated. Entries are not entities (they record no events), so this
    is not a ``BaseRepository``.
    """

    @abstractmethod
    async def add_many(self, entries: list[TaskHistoryEntry]) -> None:
        """Append entries, keeping their order."""

    @abstractmethod
    async def list_for_task(
        self, task_id: TaskId, user_id: UserId
    ) -> list[TaskHistoryEntry]:
        """One task's history, oldest first (in the order it was written)."""
