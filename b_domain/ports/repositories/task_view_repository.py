from abc import ABC, abstractmethod
from datetime import datetime

from b_domain.value_objects.identifiers import UserId
from b_domain.value_objects.task_view import TaskView, ViewScope


class TaskViewRepository(ABC):
    """The saved views: this device's own and the account's (which sync).

    Views record no events, so this is not a ``BaseRepository``.
    """

    @abstractmethod
    async def list_by_user(self, user_id: UserId) -> list[TaskView]:
        """Every view of the user seen here, both scopes, by name."""

    @abstractmethod
    async def save(self, view: TaskView) -> None:
        """Keep a view, replacing one of the same name and scope."""

    @abstractmethod
    async def remove(
        self, user_id: UserId, name: str, scope: ViewScope, now: datetime
    ) -> bool:
        """Forget a view; whether there was one. Every device's is forgotten
        on every device (``now`` is when, for sync)."""
