from abc import ABC, abstractmethod

from a_core.base import DomainEvent


class EventBus(ABC):
    """Outbound port for publishing domain events.

    The EventBus defines the contract for event-driven communication
    within the domain. Implementations may deliver events to message
    brokers, logging systems, or in-memory subscribers.

    This abstraction ensures that domain logic remains decoupled from
    infrastructure concerns.
    """

    @abstractmethod
    async def publish(self, event: DomainEvent) -> None:
        """Publish a domain event asynchronously.

        Args:
            event (DomainEvent): The domain event to be published.

        Returns:
            None

        Raises:
            Exception: Implementations may raise errors if publishing fails.
        """
