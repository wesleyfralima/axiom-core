from dataclasses import dataclass
from typing import ClassVar

from a_core.base import TextValueObject


@dataclass(frozen=True, eq=False, repr=False)
class Title(TextValueObject):
    """Represents a title with validation rules.

    The value will be automatically stripped of leading/trailing whitespaces
    and validated against length constraints.
    """

    ALLOW_NONE: ClassVar[bool] = False
    MAX_LENGTH: ClassVar[int] = 255
    MIN_LENGTH: ClassVar[int] = 3
    STRIP: ClassVar[bool] = True


@dataclass(frozen=True, eq=False, repr=False)
class Description(TextValueObject):
    """Represents a description with validation rules."""

    ALLOW_NONE: ClassVar[bool] = True
    MAX_LENGTH: ClassVar[int] = 5000
    MIN_LENGTH: ClassVar[int] = 0
    STRIP: ClassVar[bool] = False
