from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

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
    async def recent(self, user_id: UserId, limit: int = 200) -> list[TaskHistoryEntry]:
        """The user's latest entries, newest first (what undo walks back)."""

    @abstractmethod
    async def caused_by(self, entry_id: UUID) -> list[TaskHistoryEntry]:
        """The entries another entry's change made on its own."""

    @abstractmethod
    async def between(
        self, user_id: UserId, start: datetime, end: datetime
    ) -> list[TaskHistoryEntry]:
        """The user's entries from ``start`` (included) to ``end`` (excluded),
        oldest first — what a report counts."""

    @abstractmethod
    async def list_for_tasks(
        self, task_ids: list[TaskId], user_id: UserId
    ) -> list[TaskHistoryEntry]:
        """Several tasks' history together (a series), oldest first."""

    @abstractmethod
    async def list_for_task(
        self, task_id: TaskId, user_id: UserId
    ) -> list[TaskHistoryEntry]:
        """One task's history, oldest first (in the order it was written)."""
