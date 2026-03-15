from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from a_core.ddd.events import DomainEvent
from a_core.ddd.identities import UniqueId


@dataclass(kw_only=True)
class Entity:
    """Base class for all domain Entities (e.g., Task, User, Context).

    An Entity is defined by its Identity (ID), rather than its attributes.
    This guarantees that business logic handles unique, traceable objects
    regardless of how their internal data might change over time.
    """

    id: UniqueId = field(default_factory=lambda: UniqueId())
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Internal list of unpublished domain events
    _domain_events: list[DomainEvent] = field(default_factory=list, repr=False, init=False)

    def __eq__(self, other: Any) -> bool:
        """Entities are considered equal if they share the same business ID.

        Args:
            other (Any): The object to compare against.

        Returns:
            bool: True if the IDs match and types are compatible, False otherwise.
        """
        if isinstance(other, type(self)):
            return self.id == other.id
        return False

    def __hash__(self) -> int:
        """Generate a hash based on the entity's unique ID."""
        return hash(self.id)

    def _touch(self, now: datetime) -> None:
        """Update the modification timestamp."""
        self.updated_at = now

    def add_event(self, event: DomainEvent) -> None:
        """Register a new domain event that occurred in this entity.

        Args:
            event (DomainEvent): The domain event to record.
        """
        self._domain_events.append(event)

    def pull_events(self) -> list[DomainEvent]:
        """Extract all recorded domain events and clear the internal list.

        Returns:
            List[DomainEvent]: The list of domain events that were recorded.
        """
        events: list[DomainEvent] = self._domain_events[:]
        self._domain_events.clear()
        return events
