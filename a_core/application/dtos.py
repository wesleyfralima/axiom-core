from abc import ABC
from dataclasses import dataclass
from typing import TypeVar, Generic

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
