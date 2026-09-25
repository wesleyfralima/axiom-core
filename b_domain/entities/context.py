from dataclasses import dataclass, field
from datetime import datetime

from a_core import Entity
from a_core.exceptions import ValidationException
from b_domain.value_objects import UserId
from b_domain.value_objects.identifiers import ContextId

DEFAULT_CONTEXT_ICON = "🏷️"


@dataclass(kw_only=True, eq=False)
class Context(Entity):
    """Represents the 'where' or 'how' a task should be performed.

    Examples:
        - "Street" (location-based context)
        - "Work" (professional context)
        - "Focused" (mental state context)

    Names are unique per user, ignoring case; that rule needs the user's other
    contexts, so the use cases enforce it.

    Attributes:
        user_id (UserId): Identifier of the user who owns this context.
        name (str): Human-readable name of the context.
        icon (str): Emoji or symbol representing the context (default: 🏷️).
        description (str): Optional descriptive text for the context.
    """

    NAME_MAX_LENGTH = 100
    ICON_MAX_LENGTH = 20

    id: ContextId = field(default_factory=ContextId)
    user_id: UserId
    name: str
    icon: str = DEFAULT_CONTEXT_ICON
    description: str = ""

    @classmethod
    def create(
        cls,
        now: datetime,
        user_id: UserId,
        name: str,
        icon: str | None = None,
        description: str | None = None,
    ) -> "Context":
        """Factory method to create a new Context entity.

        Args:
            now (datetime): Current timestamp.
            user_id (UserId): Identifier of the user who owns this context.
            name (str): Name of the context (e.g., "Work", "Home").
            icon (str | None): Emoji or symbol representing the context.
                Defaults to 🏷️.
            description (str | None): Optional descriptive text.

        Returns:
            Context: A new Context entity with the given attributes.

        Raises:
            ValidationException: If the name or the icon is empty or too long.
        """
        return cls(
            user_id=user_id,
            name=cls._clean_name(name),
            icon=cls._clean_icon(icon),
            description=(description or "").strip(),
            created_at=now,
            updated_at=now,
        )

    def update(
        self,
        now: datetime,
        name: str | None = None,
        icon: str | None = None,
        description: str | None = None,
    ) -> None:
        """Change the given attributes; the ones left as None stay as they are.

        Args:
            now (datetime): Current timestamp.
            name (str | None): New name.
            icon (str | None): New icon.
            description (str | None): New description ("" clears it).

        Raises:
            ValidationException: If the name or the icon is empty or too long.
        """
        if name is not None:
            self.name = self._clean_name(name)
        if icon is not None:
            self.icon = self._clean_icon(icon)
        if description is not None:
            self.description = description.strip()
        self._touch(now)

    def matches_name(self, name: str) -> bool:
        """Whether ``name`` is this context's name, ignoring case and spaces."""
        return self.name.casefold() == name.strip().casefold()

    @classmethod
    def _clean_name(cls, name: str) -> str:
        clean: str = name.strip()
        if not clean:
            raise ValidationException("Context name cannot be empty.")
        if len(clean) > cls.NAME_MAX_LENGTH:
            raise ValidationException(
                f"Context name cannot be longer than {cls.NAME_MAX_LENGTH} characters."
            )
        return clean

    @classmethod
    def _clean_icon(cls, icon: str | None) -> str:
        if icon is None:
            return DEFAULT_CONTEXT_ICON
        clean: str = icon.strip()
        if not clean:
            raise ValidationException("Context icon cannot be empty.")
        if len(clean) > cls.ICON_MAX_LENGTH:
            raise ValidationException(
                f"Context icon cannot be longer than {cls.ICON_MAX_LENGTH} characters."
            )
        return clean
