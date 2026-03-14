from abc import ABC, abstractmethod

from b_domain.entities.outbox_event import OutboxEvent


class OutboxEventRepository(ABC):
    """Repository interface for managing Outbox events.

    This repository defines the contract for persisting and retrieving
    Outbox events, which are used to reliably deliver domain events
    to external systems (supporting the Outbox pattern).
    """

    @abstractmethod
    async def add_many(self, events: list[OutboxEvent]) -> None:
        """Persist multiple new Outbox events.

        Typically called by the UnitOfWork after extracting domain events
        from tracked entities.

        Args:
            events (list[OutboxEvent]): The events to persist.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_unprocessed(self, limit: int = 50) -> list[OutboxEvent]:
        """Retrieve unprocessed Outbox events.

        Only returns events that have not yet been marked as processed
        and respect their scheduled execution time.

        Args:
            limit (int, optional): Maximum number of events to fetch.
                Defaults to 50.

        Returns:
            list[OutboxEvent]: A list of unprocessed events.
        """
        raise NotImplementedError

    @abstractmethod
    async def update(self, event: OutboxEvent) -> None:
        """Update an Outbox event.

        Used to mark events as processed, increment retry counts,
        or record error details.

        Args:
            event (OutboxEvent): The event to update.
        """
        raise NotImplementedError
