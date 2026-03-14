"""Core base classes for Domain Driven Design (DDD) and Application use cases."""

import inspect
from abc import ABC
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, ClassVar, Generic, List, Optional, TypeVar
from uuid import UUID, uuid4

from a_core.exceptions import ValidationException


# ==========================================
# DOMAIN FOUNDATIONS
# ==========================================

@dataclass(kw_only=True)
class Entity:
    """Base class for all domain Entities (e.g., Task, User, Context).

    An Entity is defined by its Identity (ID), rather than its attributes.
    This guarantees that the business logic handles unique, traceable objects
    regardless of how their internal data might change over time.
    """

    id: "UniqueId" = field(default_factory=lambda: UniqueId())
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Lista interna de eventos não publicados
    _domain_events: List["DomainEvent"] = field(default_factory=list, repr=False, init=False)

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
        """Generates a hash based on the entity's unique ID."""
        return hash(self.id)

    def _touch(self, now: datetime) -> None:
        """Update the modification timestamp."""
        self.updated_at = now

    def add_event(self, event: "DomainEvent") -> None:
        """Registra um novo evento ocorrido nesta entidade."""
        self._domain_events.append(event)

    def pull_events(self) -> List["DomainEvent"]:
        """Extrai todos os eventos e limpa a lista interna."""
        events = self._domain_events[:]
        self._domain_events.clear()
        return events


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    """Base class for all domain events.

    A domain event represents a fact that has already occurred in the system
    and is relevant to the business domain. Events are immutable and carry
    metadata for tracking and correlation.
    """

    id: "UniqueId" = field(default_factory=lambda: UniqueId())
    """Unique event ID (may ensure idempotency)."""

    occurred_on: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    """Exact moment when the fact occurred (always stored in UTC at the root level)"""

    correlation_id: Optional["UniqueId"] = None
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
        data.pop("id", None)
        data.pop("correlation_id", None)
        data.pop("occurred_on", None)

        return data


@dataclass(frozen=True, kw_only=True)
class ValueObject(ABC):
    """Base class for all Value Objects.

    Value Objects are immutable. Two value objects are considered equal
    if all their attributes are exactly the same. They do not have a unique ID.
    """


@dataclass(frozen=True)
class UniqueId(ValueObject):
    """Strongly typed unique identifier based on UUID."""

    value: UUID = field(default_factory=uuid4)

    def __str__(self) -> str:
        """Return the string representation of the UUID."""
        return str(self.value)

    @classmethod
    def from_string(cls, value: str) -> "UniqueId":
        """Create a UniqueId from a string.

        Args:
            value (str): The string representation of the VALID UUID.

        Raises:
            ValidationException: If the string representation is not a valid UUID.
        """
        try:
            return cls(UUID(value))
        except ValueError:
            raise ValidationException(f"The provided value is not a valid UUID: {value}")


@dataclass(frozen=True)
class IdPrefix(ValueObject):
    """Strong identifier for IDs prefixes."""

    value: str

    def __post_init__(self):
        if len(self.value) < 4:
            raise ValidationException(
                "The ID prefix must be at least 4 characters long."
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class TextValueObject(ValueObject):
    """Base class for string-based value objects with validation rules."""

    value: Optional[str] = None

    # We use ClassVar to ensure these configurations do NOT become
    # __init__ arguments. They are constants defined by child classes.
    MIN_LENGTH: ClassVar[Optional[int]] = None
    MAX_LENGTH: ClassVar[Optional[int]] = None
    ALLOW_NONE: ClassVar[bool] = True
    STRIP: ClassVar[bool] = False

    def __post_init__(self) -> None:
        """Validate the string value after initialization."""

        val: str | None = self.value

        # None check
        if val is None and not self.ALLOW_NONE:
            raise ValidationException(f"{self.__class__.__name__} cannot be None.")

        if val is not None:

            # Apply stripping if enabled
            if self.STRIP:
                val = val.strip()

            # Validate minimum length
            if self.MIN_LENGTH is not None and len(val) < self.MIN_LENGTH:
                raise ValidationException(
                    f"{self.__class__.__name__} must have at least {self.MIN_LENGTH} characters."
                )

            # Validate maximum length
            if self.MAX_LENGTH is not None and len(val) > self.MAX_LENGTH:
                raise ValidationException(
                    f"{self.__class__.__name__} cannot exceed {self.MAX_LENGTH} characters."
                )

            # Execute subclass-specific custom validation
            self.validate(val)

        # Update value safely within a frozen dataclass
        object.__setattr__(self, "value", val)

    def validate(self, value: str) -> None:
        """Hook for subclass-specific validation rules.

        Subclasses can override this method to inject custom logic
        (e.g., regex pattern matching, forbidden words) without
        needing to override __post_init__.
        """

    def __eq__(self, other: Any) -> bool:
        """Compare equality with another object.

        - If `other` is a string, compare directly with `value`.
        - If `other` is the same class, compare their `value`.
        - Otherwise, return False.
        """
        if isinstance(other, str):
            return self.value == other
        if isinstance(other, self.__class__):
            return self.value == other.value
        return False

    def __repr__(self) -> str:
        """Return a developer-friendly string representation."""
        return f"{self.__class__.__name__}(value={self.value!r})"

    def __str__(self) -> str:
        """Return the string representation of the value object."""
        return str(self.value) if self.value is not None else ""


# ==========================================
# APPLICATION FOUNDATIONS
# ==========================================

def tracks_entity(method: Callable):
    """Decorator that automatically registers repository results in the Unit of Work.

    This ensures that any entity retrieved by repository methods (e.g., `get_by_id`)
    is tracked by the Unit of Work for change detection and persistence.

    Args:
        method (Callable): The repository method being decorated.

    Returns:
        Callable: Wrapped method that tracks returned entities.
    """

    @wraps(method)
    async def wrapper(self: "BaseRepository", *args, **kwargs):

        # Execute the original repository method
        result: Any = await method(self, *args, **kwargs)

        # If the result is an entity or list of entities, track them
        if result:
            if isinstance(result, list):
                for item in result:
                    self._track(item)
            else:
                self._track(result)

        return result

    # Marker attribute: indicates this method is safely tracked
    wrapper._is_tracked = True
    return wrapper


# Generic type for Output (Response)
TResponse: TypeVar = TypeVar("TResponse")


class DTO(ABC):
    """Base class for Data Transfer Objects (DTO).

    Serves as an abstract marker class for objects used to
    transfer data between application layers.
    """


@dataclass(kw_only=True)
class PaginatedResponse(DTO, Generic[TResponse]):
    items: list[TResponse]
    total: int
    page: int
    size: int


@dataclass(frozen=True)
class Result(Generic[TResponse]):
    is_success: bool
    value: Optional[TResponse] = None
    error: Optional[str] = None


class BaseRepository:
    """Base class for repositories with automatic entity tracking.

    Ensures that any repository method responsible for retrieving or
    adding entities is decorated with `@tracks_entity`. This guarantees
    that entities are tracked by the Unit of Work for change detection
    and persistence.
    """

    def __init__(self, seen_entities: set):
        """Initialize the repository.

        Args:
            seen_entities (set): A shared set of entities tracked by the Unit of Work.
        """
        self._seen_entities = seen_entities

    def _track(self, entity):
        """Track an entity if it supports domain events.

        Entities with a `pull_events` method are added to the Unit of Work's
        tracked set, enabling event dispatch and persistence.
        """
        if hasattr(entity, "pull_events"):
            self._seen_entities.add(entity)

    def __init_subclass__(cls, **kwargs):
        """Validate repository subclass methods at definition time.

        This hook inspects all coroutine methods in subclasses. If a method
        appears to be a query or mutation (e.g., starts with `get`, `find`,
        `list`, or `add`) but is not decorated with `@tracks_entity`, an
        error is raised to enforce architectural consistency.
        """

        super().__init_subclass__(**kwargs)

        # Inspector: scans the class for coroutine methods
        for name, method in inspect.getmembers(cls, predicate=inspect.iscoroutinefunction):

            # Ignore private methods or those inherited from BaseRepository
            if name.startswith("_") or name in dir(BaseRepository):
                continue

            # Enforce tracking for repository methods
            if name.startswith(("get", "find", "list", "add")):
                if not getattr(method, "_is_tracked", False):
                    raise TypeError(
                        f"\n[ARCHITECTURE ERROR] The method '{cls.__name__}.{name}' "
                        f"must be decorated with @tracks_entity to ensure tracking."
                    )
