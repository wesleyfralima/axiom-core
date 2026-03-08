"""Core base classes for Domain Driven Design (DDD) and Application use cases."""

from abc import ABC
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar, Optional, ClassVar, List
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
    """
    Classe base para todos os eventos de domínio.
    Representa um fato que já ocorreu no sistema e que é de interesse do negócio.
    """

    # ID único do evento (garante idempotência se usarmos mensageria no futuro)
    event_id: UUID = field(default_factory=uuid4, init=False)

    # Momento exato em que o fato ocorreu (sempre em UTC na raiz)
    occurred_on: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
        init=False
    )


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


@dataclass(frozen=True)
class TextValueObject(ValueObject):
    """Base class for string-based value objects with validation rules."""

    value: Optional[str] = None

    # Usamos ClassVar para garantir que estas configurações NÃO se tornem
    # argumentos do __init__. Elas são constantes da classe filha.
    MIN_LENGTH: ClassVar[Optional[int]] = None
    MAX_LENGTH: ClassVar[Optional[int]] = None
    ALLOW_NONE: ClassVar[bool] = True
    STRIP: ClassVar[bool] = False

    def __post_init__(self) -> None:
        """Validate the string value after initialization."""

        val = self.value

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
        needing to override __post_init__ or use lambda hooks.
        """

    def __eq__(self, other: Any) -> bool:
        """Compare equality with another object."""

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
