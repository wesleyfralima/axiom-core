from dataclasses import replace
from datetime import datetime, timezone, timedelta
from logging import getLogger, Logger
from typing import Type, Dict

from a_core import DomainEvent
from b_domain.entities.outbox_event import OutboxEvent
from b_domain.ports.event_bus import EventBus
from b_domain.ports.repositories.outbox_event_repository import OutboxEventRepository

logger: Logger = getLogger(__name__)


class OutboxRelayService:
    """Domain service responsible for dispatching Outbox events to the EventBus.

    This service orchestrates the reliable delivery of domain events
    stored in the Outbox. It supports rehydration of events, publishing
    via the EventBus, and retry logic with exponential backoff.
    """

    def __init__(
            self,
            outbox_repo: OutboxEventRepository,
            event_bus: EventBus,
            event_registry: Dict[str, Type[DomainEvent]],
    ):
        """Initialize the relay service.

        Args:
            outbox_repo (OutboxEventRepository): Repository for managing Outbox entries.
            event_bus (EventBus): Outbound port for publishing domain events.
            event_registry (Dict[str, Type[DomainEvent]]): Registry mapping event names
                to DomainEvent classes (used for rehydration).
        """
        self.outbox_repo = outbox_repo
        self.event_bus = event_bus
        self.event_registry = event_registry

    async def relay_pending_events(self, limit: int = 50) -> int:
        """Fetch and publish pending Outbox events.

        Steps:
            1. Retrieve unprocessed events that are scheduled for dispatch.
            2. Rehydrate payloads into DomainEvent instances.
            3. Publish events via the EventBus.
            4. Mark successful events as processed.
            5. Apply retry logic for failures.

        Args:
            limit (int, optional): Maximum number of events to process. Defaults to 50.

        Returns:
            int: Total number of successfully processed events.
        """

        pending_entries: list[OutboxEvent] = await self.outbox_repo.get_unprocessed(limit=limit)
        processed_count: int = 0

        for entry in pending_entries:
            try:
                # Rehydrate payload into a DomainEvent instance
                domain_event: DomainEvent = self._rehydrate(entry)

                # Publish via EventBus
                await self.event_bus.publish(domain_event)

                # Mark success
                entry.processed_at = datetime.now(timezone.utc)
                processed_count += 1

            except Exception as e:
                # Apply retry logic with exponential backoff
                self._handle_failure(entry, str(e))
                logger.error(f"Failed to dispatch event {entry.event_id}: {e}")

            finally:
                # Persist updated state (success or failure)
                await self.outbox_repo.update(entry)

        return processed_count

    def _rehydrate(self, entry: OutboxEvent) -> DomainEvent:
        """Convert an Outbox entry back into a DomainEvent instance.

        Args:
            entry (OutboxEvent): The Outbox entry to rehydrate.

        Returns:
            DomainEvent: The reconstructed domain event.

        Raises:
            ValueError: If the event class cannot be found in the registry.
        """

        event_class: type[DomainEvent] = self.event_registry.get(entry.event_name)
        if not event_class:
            raise ValueError(f"Event class not found in registry: {entry.event_name}")

        event: DomainEvent = event_class.from_dict(entry.payload)

        return replace(
            event,
            id=entry.event_id,
            occurred_at=entry.occurred_at,
            correlation_id=entry.correlation_id,
        )

    @staticmethod
    def _handle_failure(entry: OutboxEvent, error_message: str) -> None:
        """Apply exponential backoff scheduling after a failure.

        Args:
            entry (OutboxEvent): The failed Outbox event.
            error_message (str): Error message describing the failure.
        """

        entry.retry_count += 1
        entry.last_error = error_message

        # Exponential backoff strategy:
        # 1st retry = 1min, 2nd = 2min, 3rd = 4min, etc.
        wait_minutes = entry.retry_count ** 2
        entry.scheduled_for = datetime.now(timezone.utc) + timedelta(minutes=wait_minutes)
