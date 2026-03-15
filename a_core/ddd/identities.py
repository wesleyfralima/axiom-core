from dataclasses import dataclass, field
from uuid import UUID, uuid4

from a_core.ddd.value_objects import ValueObject
from a_core.exceptions import ValidationException


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
