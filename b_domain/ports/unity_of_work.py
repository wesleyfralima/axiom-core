import logging
from abc import ABC, abstractmethod
from types import TracebackType
from typing import Optional, Self, Type

from a_core import Entity
from a_core.base import DomainEvent
from b_domain.entities.outbox_event import OutboxEvent
from b_domain.ports.event_bus import EventBus
from b_domain.ports.repositories import TaskRepository, UserRepository
from b_domain.ports.repositories.outbox_event_repository import OutboxEventRepository
from b_domain.ports.repositories.time_entry_repository import TimeEntryRepository
from b_domain.ports.repositories.user_behavior_metrics_repository import UserBehaviorMetricsRepository
from b_domain.ports.repositories.user_behavior_profile_repository import UserBehaviorProfileRepository

logger: logging.Logger = logging.getLogger(__name__)


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
    outbox_repo: OutboxEventRepository
    user_behavior_metrics: UserBehaviorMetricsRepository
    user_behavior_profiles: UserBehaviorProfileRepository

    def __init__(self, event_bus: EventBus):
        """Initialize the UnitOfWork with an event bus.

        Args:
            event_bus (EventBus): Event bus used to publish domain events.
        """
        self.event_bus = event_bus
        self._seen_entities: set[Entity] = set()

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

        # Guard clause:
        # If an exception occurred inside the `async with` block,
        # ensure rollback and propagate the exception.
        if exc_type is not None:
            await self.rollback()
            return

        try:
            await self._process_events()
            await self.commit()

            # Notify the system that new events are available in the outbox.
            # If this fails, background workers will eventually pick them up.
            try:
                await self.event_bus.trigger_relay()
            except Exception as e:
                logger.exception(f"Unknown exception while triggering relay: {e}")

        except Exception:
            # If commit fails (e.g., network failure, integrity error),
            # ensure rollback and propagate the exception.
            await self.rollback()
            raise

    async def _process_events(self) -> None:
        """Extract domain events from tracked entities and prepare them for the Outbox."""

        outbox_entries: list[OutboxEvent] = []

        for entity in self._seen_entities:
            for event in entity.pull_events():
                outbox_entries.append(self._to_outbox(event))

        if outbox_entries:
            await self.outbox_repo.add_many(outbox_entries)

        # Clear tracked entities after processing
        self._seen_entities.clear()

    @staticmethod
    def _to_outbox(event: DomainEvent) -> OutboxEvent:
        """Convert a DomainEvent into an OutboxEvent for persistence."""
        return OutboxEvent(
            event_id=event.id,
            correlation_id=getattr(event, "correlation_id", None),
            event_name=event.event_name(),
            event_version=event.event_version(),
            aggregate_type=getattr(event, "AGGREGATE_TYPE", None),
            payload=event.to_payload(),
            occurred_at=event.occurred_at,
        )

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
