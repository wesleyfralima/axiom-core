from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Any

from a_core import Entity, UniqueId


@dataclass(kw_only=True)
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
    aggregate_type: Optional[str] = None
    correlation_id: Optional[UniqueId] = None

    # Structured payload of the domain event
    payload: dict[str, Any]

    # Timestamp when the event occurred in the domain
    occurred_at: datetime

    # Processing metadata
    processed_at: Optional[datetime] = None

    # Retry metadata
    retry_count: int = 0
    last_error: Optional[str] = None
    scheduled_for: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_processed(self) -> bool:
        """Check if the event has already been processed.

        Returns:
            bool: True if the event has been processed, False otherwise.
        """
        return self.processed_at is not None
