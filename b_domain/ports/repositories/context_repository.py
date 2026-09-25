from abc import ABC, abstractmethod

from a_core import BaseRepository, tracks_entity
from b_domain.entities import Context
from b_domain.value_objects import UserId
from b_domain.value_objects.identifiers import ContextId


class ContextRepository(ABC, BaseRepository):
    """Contract for Context persistence operations.

    A user has few contexts, so the use cases load them all
    (``list_by_user``) and resolve names and id prefixes in memory.
    """

    @abstractmethod
    @tracks_entity
    async def add(self, context: Context) -> None:
        """Add a new context.

        Args:
            context (Context): The context to add.
        """

    @abstractmethod
    async def update(self, context: Context) -> None:
        """Persist the changes made to an existing context.

        Args:
            context (Context): The context with updated values.
        """

    @abstractmethod
    async def delete(self, context_id: ContextId) -> None:
        """Permanently remove a context.

        Tasks that referenced it **must** lose the reference (their
        ``context_id`` becomes None); they are not deleted.

        Args:
            context_id (ContextId): The ID of the context to delete.
        """

    @abstractmethod
    @tracks_entity
    async def get_by_id(self, context_id: ContextId, user_id: UserId) -> Context | None:
        """Retrieve one of the user's contexts by its ID.

        Args:
            context_id (ContextId): The context's unique identifier.
            user_id (UserId): The owner; another user's context is not found.

        Returns:
            Context | None: The context if found, otherwise None.
        """

    @abstractmethod
    @tracks_entity
    async def list_by_user(self, user_id: UserId) -> list[Context]:
        """Return all of the user's contexts, sorted by name (case-insensitive).

        Args:
            user_id (UserId): The owner.

        Returns:
            list[Context]: The user's contexts.
        """
