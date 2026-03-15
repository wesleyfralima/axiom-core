from abc import ABC, abstractmethod
from typing import Sequence, Type, Any

from a_core import DomainEvent


class EventBus(ABC):
    """Outbound port for publishing domain events.

    The EventBus defines the contract for event-driven communication
    within the domain. Implementations may deliver events to message
    brokers, logging systems, or in-memory subscribers.

    This abstraction ensures that domain logic remains decoupled from
    infrastructure concerns.
    """

    @abstractmethod
    def subscribe(self, event_type: Type[DomainEvent], handler: Any) -> None:
        """Register a handler for a specific domain event type.

        The handler must implement an asynchronous `handle(event)` method,
        which will be invoked whenever an event of the given type is published.

        Args:
            event_type (Type[DomainEvent]): The class of the domain event to subscribe to.
            handler (Any): The handler instance that processes the event.
        """

    @abstractmethod
    async def publish(self, event: DomainEvent) -> None:
        """Publish a single domain event asynchronously.

        Args:
            event (DomainEvent): The domain event to be published.

        Raises:
            Exception: Implementations may raise errors if publishing fails.
        """

    @abstractmethod
    async def publish_many(self, events: Sequence[DomainEvent]) -> None:
        """Publish multiple domain events asynchronously.

        Args:
            events (Sequence[DomainEvent]): A sequence of domain events to publish.

        Raises:
            Exception: Implementations may raise errors if publishing fails.
        """
        raise NotImplementedError

    @abstractmethod
    async def trigger_relay(self) -> None:
        """Trigger an outbox relay mechanism.

        This method is typically used to notify the system that new events
        are available in the outbox, prompting background workers or
        subscribers to process them.
        """
        raise NotImplementedError
