from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from a_core import DomainEvent, Entity, UniqueId


@dataclass(kw_only=True, eq=False)
class OutboxEvent(Entity):
    """Represents a domain event stored in the Outbox.

    Outbox events are persisted to ensure reliable delivery of domain events
    to external systems (e.g., message brokers). This supports the Outbox
    pattern, guaranteeing eventual consistency between the domain model and
    event-driven infrastructure.
    """

    # Original domain event ID (ensures idempotency)
    event_id: UniqueId

    # Envelope metadata
    event_name: str
    event_version: int
    aggregate_type: str | None = None
    correlation_id: UniqueId | None = None

    # Structured payload of the domain event
    payload: dict[str, Any]

    # Timestamp when the event occurred in the domain
    occurred_at: datetime

    # Processing metadata
    processed_at: datetime | None = None

    # Retry metadata
    retry_count: int = 0
    last_error: str | None = None
    scheduled_for: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_processed(self) -> bool:
        """Check if the event has already been processed.

        Returns:
            bool: True if the event has been processed, False otherwise.
        """
        return self.processed_at is not None

    def add_event(self, event: DomainEvent) -> None:
        """Disables event recording for OutboxEvent entities.

        OutboxEvent is a persistence mechanism used to store other domain events.
        Allowing it to record its own events could lead to infinite recursion
        (e.g., an OutboxEvent triggering the creation of another OutboxEvent).
        Therefore, this operation is explicitly disallowed.

        Raises:
            ValueError: Always raised to prevent event recording on this entity type.
        """
        raise ValueError("OutboxEvent entities do not support adding events")

    def pull_events(self) -> list[DomainEvent]:
        """Returns an empty list of domain events.

        Overridden to ensure that the Unit of Work and Repository tracking
        mechanisms treat this entity as "silent." This prevents the system
        from attempting to process or re-persist metadata from the outbox
        infrastructure itself.

        Returns:
            List[DomainEvent]: An empty list, as OutboxEvents never emit domain events.
        """
        return []
