import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import ClassVar

from a_core import TextValueObject
from a_core.exceptions import ValidationException


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


TAG_MAX_LENGTH: int = 30

_TAG_RE: re.Pattern[str] = re.compile(r"^[\w-]+$")


def normalize_tag(text: str) -> str:
    """A tag as stored: lower case, without the ``#`` it may be typed with.

    Raises:
        ValidationException: If it is empty, too long, or has anything but
            letters, digits, ``-`` and ``_``.
    """
    tag: str = text.strip().lstrip("#").lower()
    if not tag or len(tag) > TAG_MAX_LENGTH or not _TAG_RE.match(tag):
        raise ValidationException(
            f"A tag is letters, digits, - or _ (up to {TAG_MAX_LENGTH}): '{text}'."
        )
    return tag


def normalize_tags(texts: Iterable[str]) -> frozenset[str]:
    """Several tags; each text may hold a few, separated by commas or spaces.

    Raises:
        ValidationException: If one of them is not a valid tag.
    """
    return frozenset(
        normalize_tag(part) for text in texts for part in text.replace(",", " ").split()
    )
