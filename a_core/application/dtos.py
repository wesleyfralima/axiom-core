from abc import ABC
from dataclasses import dataclass


class DTO(ABC):  # noqa: B024 - marker class, no abstract methods
    """Base class for Data Transfer Objects (DTO).

    Serves as an abstract marker class for objects used to
    transfer data between application layers.
    """


class InputDTO(DTO):
    """Base class for Input Objects (DTO)."""


class OutputDTO(DTO):
    """Base class for Output Objects (DTO)."""


@dataclass(kw_only=True)
class PaginatedResponse[D: OutputDTO](DTO):
    items: list[D]
    total_items: int
    per_page: int
    total_pages: int
    current_page: int
