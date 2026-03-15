from abc import ABC
from dataclasses import dataclass
from typing import Optional, ClassVar, Any

from a_core.exceptions import ValidationException


@dataclass(frozen=True, kw_only=True)
class ValueObject(ABC):
    """Base class for all Value Objects.

    Value Objects are immutable. Two value objects are considered equal
    if all their attributes are exactly the same. They do not have a unique ID.
    """


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
