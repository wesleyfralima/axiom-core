from dataclasses import dataclass, field
from typing import Self
from uuid import UUID, uuid4

from a_core.ddd.value_objects import SimpleValueObject, TextValueObject
from a_core.exceptions import ValidationException


@dataclass(frozen=True)
class UniqueId(SimpleValueObject):
    """Strongly typed unique identifier based on UUID."""

    value: UUID = field(default_factory=uuid4)

    def __str__(self) -> str:
        """Return the string representation of the UUID."""
        return str(self.value)

    @classmethod
    def from_string(cls, value: str, *, error_msg: str | None = None) -> Self:
        """Create a UniqueId from a string.

        Args:
            value (str): The string representation of the VALID UUID.
            error_msg (Optional[str]): Optional error message if the UUID is invalid.

        Raises:
            ValidationException: If the string representation is not a valid UUID.
        """
        try:
            return cls(UUID(value))
        except ValueError:
            raise ValidationException(
                error_msg or f"The provided value is not a valid UUID: {value}"
            )


@dataclass(frozen=True)
class IdPrefix(TextValueObject):
    """Strong identifier for IDs prefixes."""

    value: str

    ALLOW_NONE = False
    STRIP = True
    MIN_LENGTH = 4
    MAX_LENGTH = 32
