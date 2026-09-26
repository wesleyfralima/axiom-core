"""Every domain event by name: what the outbox relay needs to read them back.

Interfaces hand this to the relay instead of keeping their own list — an
event missing from it fails on every relay and is retried forever.
"""

from a_core import DomainEvent
from b_domain.events import other_events, task_events

EVENT_REGISTRY: dict[str, type[DomainEvent]] = {
    cls.__name__: cls
    for module in (task_events, other_events)
    for cls in vars(module).values()
    if isinstance(cls, type)
    and issubclass(cls, DomainEvent)
    and cls is not DomainEvent
    and cls.__module__ == module.__name__
}
