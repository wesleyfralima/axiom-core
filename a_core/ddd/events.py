from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, ClassVar, Any

from a_core.ddd.identities import UniqueId


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    """Base class for all domain events.

    A domain event represents a fact that has already occurred in the system
    and is relevant to the business domain. Events are immutable and carry
    metadata for tracking and correlation.
    """

    id: UniqueId = field(default_factory=lambda: UniqueId())
    """Unique event ID (may ensure idempotency)."""

    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    """Exact moment when the fact occurred (always stored in UTC at the root level)"""

    correlation_id: Optional[UniqueId] = None
    """Correlation ID allows tracking which command/request originated this event."""

    # Metadata constants
    EVENT_VERSION: ClassVar[int] = 1
    AGGREGATE_TYPE: ClassVar[Optional[str]] = None

    def event_name(self) -> str:
        """Return the canonical name of the event (class name)."""
        return self.__class__.__name__

    def event_version(self) -> int:
        """Return the version of the event schema."""
        return self.EVENT_VERSION

    def to_payload(self) -> dict[str, Any]:
        """Controlled serialization of event payload.

        Converts the event into a dictionary suitable for persistence
        or messaging, excluding envelope metadata such as IDs and timestamps.
        """

        data: dict[str, Any] = asdict(self)

        # Remove envelope metadata
        data.pop("AGGREGATE_TYPE", None)

        return data
