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
        except ValueError as e:
            raise ValidationException(
                error_msg or f"The provided value is not a valid UUID: {value}"
            ) from e


@dataclass(frozen=True)
class IdPrefix(TextValueObject):
    """The start of an ID, as the user types it ("45e4", "45e45de9-55").

    Dashes and case do not count: a prefix is compared by its ``hex`` (the
    ID's 32 hex digits, lowercase, no dashes), so the short ID, a longer
    prefix and the full UUID all work.
    """

    value: str

    ALLOW_NONE = False
    STRIP = True
    MIN_LENGTH = 4
    MAX_LENGTH = 36  # a full UUID, with its dashes

    def validate(self, value: str) -> None:
        """Only hex digits and dashes, with 4 to 32 digits.

        Raises:
            ValidationException: If the prefix has other characters or too
                few/many digits.
        """
        digits: str = value.replace("-", "")
        if not all(c in "0123456789abcdefABCDEF" for c in digits):
            raise ValidationException(
                f"'{value}' is not an ID: IDs have only 0-9 and a-f."
            )
        if not 4 <= len(digits) <= 32:
            raise ValidationException(
                "IdPrefix must have at least 4 characters (and at most the "
                "32 digits of an ID)."
            )

    @property
    def hex(self) -> str:
        """The prefix as the ID's hex digits: lowercase, no dashes."""
        return self.value.replace("-", "").lower()

    def matches(self, identifier: object) -> bool:
        """Whether an ID (a UUID, or anything whose str is one) starts so."""
        return str(identifier).replace("-", "").lower().startswith(self.hex)
