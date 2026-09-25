from dataclasses import dataclass, field, fields, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any, ClassVar, get_args, get_origin
from uuid import UUID

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

    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    """Exact moment when the fact occurred (always stored in UTC at the root level)"""

    correlation_id: UniqueId | None = None
    """Correlation ID allows tracking which command/request originated this event."""

    # Metadata constants
    EVENT_VERSION: ClassVar[int] = 1
    AGGREGATE_TYPE: ClassVar[str | None] = None
    BASE_FIELDS: ClassVar[set[str]] = {"id", "occurred_at", "correlation_id"}

    def event_name(self) -> str:
        """Return the canonical name of the event (class name)."""
        return self.__class__.__name__

    def event_version(self) -> int:
        """Return the version of the event schema."""
        return self.EVENT_VERSION

    # -------------------------
    # SERIALIZATION
    # -------------------------

    def to_payload(self) -> dict[str, Any]:
        """Serialize subclass-specific fields into JSON-safe payload."""

        payload: dict[str, Any] = {}

        for f in fields(self):
            if f.name in self.BASE_FIELDS:
                continue

            value = getattr(self, f.name)
            payload[f.name] = self._serialize_value(value)

        return payload

    def _serialize_value(self, value: Any) -> Any:
        """Convert complex values into JSON-safe primitives."""

        if value is None:
            return None

        if isinstance(value, (str, int, float, bool)):
            return value

        if isinstance(value, Enum):
            return value.value

        if isinstance(value, UUID):
            return str(value)

        if isinstance(value, datetime):
            return value.isoformat()

        # Value Objects like TaskId, UserId, etc
        if hasattr(value, "value"):
            return self._serialize_value(value.value)

        if isinstance(value, (list, tuple, set)):
            return [self._serialize_value(v) for v in value]

        if isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}

        if is_dataclass(value):
            return {
                f.name: self._serialize_value(getattr(value, f.name))
                for f in fields(value)
            }

        return str(value)

    # -------------------------
    # DESERIALIZATION
    # -------------------------

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DomainEvent":
        """Reconstruct event instance from serialized payload."""

        kwargs: dict[str, Any] = {}

        for f in fields(cls):
            if f.name in cls.BASE_FIELDS:
                continue

            raw_value = data.get(f.name)
            kwargs[f.name] = cls._deserialize_value(raw_value, f.type)

        return cls(**kwargs)

    @classmethod
    def _deserialize_value(cls, value: Any, expected_type: Any) -> Any:
        """Reconstruct typed values from serialized payload."""

        # -------------------------
        # 1. None
        # -------------------------
        if value is None:
            return None

        # -------------------------
        # 2. Resolve Optional[T]
        # -------------------------
        origin = get_origin(expected_type)
        if origin is not None:
            args = get_args(expected_type)
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1:
                expected_type = non_none[0]

        # -------------------------
        # 3. Already correct type
        # -------------------------
        try:
            if isinstance(value, expected_type):
                return value
        except TypeError:
            pass

        # -------------------------
        # 4. Primitive types
        # -------------------------
        if expected_type in (str, int, float, bool):
            return expected_type(value)

        # -------------------------
        # 5. UUID
        # -------------------------
        if expected_type is UUID:
            return UUID(value)

        # -------------------------
        # 6. datetime
        # -------------------------
        if expected_type is datetime:
            return datetime.fromisoformat(value)

        # -------------------------
        # Complex types (check once)
        # -------------------------
        if isinstance(expected_type, type):
            # -------------------------
            # 7. Enum
            # -------------------------
            if issubclass(expected_type, Enum):
                return expected_type(value)

            # -------------------------
            # 8. UniqueId (TaskId, UserId etc)
            # -------------------------
            if issubclass(expected_type, UniqueId):
                if isinstance(value, str):
                    return expected_type(UUID(value))

                if isinstance(value, UUID):
                    return expected_type(value)

                return expected_type(value)

            # -------------------------
            # 9. Simple Value Objects
            # -------------------------
            from a_core import SimpleValueObject

            if issubclass(expected_type, SimpleValueObject):
                try:
                    return expected_type(value=value)
                except Exception:  # noqa
                    pass

        # -------------------------
        # 10. Safe Fallback (JSON safe)
        # -------------------------
        return str(value)
