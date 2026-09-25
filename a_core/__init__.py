"""
The `a_core` package contains the fundamental elements and building blocks
for the core application. This package has zero infrastructure dependencies
and focuses solely on pure python logic and domain rules.
"""

from a_core.application.dtos import DTO, PaginatedResponse
from a_core.ddd.entities import Entity
from a_core.ddd.events import DomainEvent
from a_core.ddd.identities import IdPrefix, UniqueId
from a_core.ddd.value_objects import SimpleValueObject, TextValueObject, ValueObject
from a_core.persistence.repository import BaseRepository, tracks_entity

from .exceptions import (
    DomainException,
    EntityNotFound,
    InvalidStateTransition,
    InvalidValueError,
    ValidationException,
)

__all__ = [
    "BaseRepository",
    "DomainEvent",
    "DTO",
    "Entity",
    "IdPrefix",
    "PaginatedResponse",
    "TextValueObject",
    "tracks_entity",
    "UniqueId",
    "ValueObject",
    "SimpleValueObject",
    "DomainException",
    "EntityNotFound",
    "InvalidStateTransition",
    "InvalidValueError",
    "ValidationException",
]
