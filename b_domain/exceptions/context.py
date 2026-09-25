from a_core.exceptions import EntityAlreadyExists


class ContextNameTakenError(EntityAlreadyExists):
    """Raised when the user already has a context with that name (any case)."""

    def __init__(self, name: str):
        super().__init__(conflicting_field="context name", identifier=name)
