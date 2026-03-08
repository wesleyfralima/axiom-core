"""
The `a_core` package contains the fundamental elements and building blocks
for the core application. This package has zero infrastructure dependencies
and focuses solely on pure python logic and domain rules.
"""

__all__ = [
    "DTO",
    "Entity",
    "PaginatedResponse",
    "UniqueId",
    "ValueObject",

    "DomainException",
    "EntityNotFound",
    "InvalidStateTransition",
    "InvalidValueError",
    "ValidationException",
]

from .base import (
    DTO,
    Entity,
    PaginatedResponse,
    UniqueId,
    ValueObject,
)
from .exceptions import (
    DomainException,
    EntityNotFound,
    InvalidStateTransition,
    InvalidValueError,
    ValidationException,
)
