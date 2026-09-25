from dataclasses import dataclass

from a_core import DTO


@dataclass(frozen=True, kw_only=True)
class ContextOutputDTO(DTO):
    """A context as the interfaces see it.

    Attributes:
        id (str): The context's unique identifier.
        name (str): Human-readable name (e.g., "Work").
        icon (str): Emoji or symbol representing the context.
        description (str): Optional descriptive text ("" when empty).
        is_active (bool): Whether it is the user's active context.
    """

    id: str
    name: str
    icon: str
    description: str = ""
    is_active: bool = False
