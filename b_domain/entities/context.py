from dataclasses import dataclass

from a_core.base import Entity
from b_domain.value_objects import UserId


@dataclass(kw_only=True)
class Context(Entity):
    """Represents the 'where' or 'how' a task should be performed.

    Examples:
        - "Street" (location-based context)
        - "Work" (professional context)
        - "Focused" (mental state context)

    Attributes:
        user_id (UserId): Identifier of the user who owns this context.
        name (str): Human-readable name of the context.
        icon (str): Emoji or symbol representing the context (default: 🏷️).
        description (str): Optional descriptive text for the context.
    """

    user_id: UserId
    name: str
    icon: str = "🏷️"
    description: str = ""

    @classmethod
    def create(cls, user_id: UserId, name: str, icon: str = "🏷️") -> "Context":
        """Factory method to create a new Context entity.

        Args:
            user_id (UserId): Identifier of the user who owns this context.
            name (str): Name of the context (e.g., "Work", "Home").
            icon (str, optional): Emoji or symbol representing the context.
                Defaults to 🏷️.

        Returns:
            Context: A new Context entity with the given attributes.
        """
        return cls(
            user_id=user_id,
            name=name,
            icon=icon
        )
