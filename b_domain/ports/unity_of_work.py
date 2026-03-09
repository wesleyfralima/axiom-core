from abc import ABC, abstractmethod
from types import TracebackType
from typing import Optional, Type, Self

from b_domain.ports.event_bus import EventBus
from b_domain.ports.repositories import TaskRepository
from b_domain.ports.repositories.time_entry_repository import TimeEntryRepository
from b_domain.ports.repositories.user_behavior_metrics_repository import UserBehaviorMetricsRepository
from b_domain.ports.repositories.user_behavior_profile_repository import UserBehaviorProfileRepository
from b_domain.ports.repositories.user_repository import UserRepository


class UnitOfWork(ABC):
    """Defines an atomic unit of work.

    A UnitOfWork:
      - Exposes repositories
      - Controls transaction boundaries
      - Publishes domain events after commit
    """

    tasks: TaskRepository
    users: UserRepository
    time_entries: TimeEntryRepository
    user_behavior_metrics: UserBehaviorMetricsRepository
    user_behavior_profiles: UserBehaviorProfileRepository

    def __init__(self, event_bus: EventBus):
        """Initialize the UnitOfWork with an event bus.

        Args:
            event_bus (EventBus): Event bus used to publish domain events.
        """
        self.event_bus = event_bus
        self._seen_entities = set()

    async def __aenter__(self) -> Self:
        """Enter the UnitOfWork context.

        Returns:
            UnitOfWork: The current UnitOfWork instance.
        """
        return self

    async def __aexit__(
            self,
            exc_type: Optional[Type[BaseException]],
            exc: Optional[BaseException],
            traceback: Optional[TracebackType],
    ) -> None:
        """Exit the UnitOfWork context.

        Commits if no exception occurred, otherwise rolls back.

        Args:
            exc_type (Optional[Type[BaseException]]): Exception type if raised.
            exc (Optional[BaseException]): Exception instance if raised.
            traceback (Optional[TracebackType]): Traceback object if available.
        """
        if exc_type is None:
            try:
                # TODO: se publicar eventos falhou, devo manter o commit?
                await self.commit()
                await self._publish_domain_events()
            except Exception:
                # If commit fails (e.g., network failure, integrity error),
                # ensure rollback and propagate the exception.
                await self.rollback()
                raise
        else:
            # If an exception occurred inside the async with block,
            # rollback and let Python propagate the exception naturally.
            await self.rollback()

    async def _publish_domain_events(self):
        """Collect domain events from tracked entities and publish them.

        Clears the internal set of seen entities after publishing.
        """
        for entity in self._seen_entities:
            for event in entity.pull_events():
                await self.event_bus.publish(event)
        self._seen_entities.clear()

    @abstractmethod
    async def commit(self) -> None:
        """Commit the current transaction.

        Implementations must ensure atomic persistence of all changes.
        """
        raise NotImplementedError

    @abstractmethod
    async def rollback(self) -> None:
        """Rollback the current transaction.

        Implementations must revert any uncommitted changes.
        """
        raise NotImplementedError
