from a_core import DomainException
from a_core.exceptions import EntityNotFound


class TaskViewNotFound(EntityNotFound):
    """No saved view has that name (the message lists the ones there are)."""

    def __init__(self, name: str, known: list[str]) -> None:
        self.entity_name = "View"
        self.identifier = name
        listed: str = ", ".join(known) or "none yet (axpro view add)"
        DomainException.__init__(
            self, f"No view called '{name}'. Your views: {listed}."
        )
