class DomainException(Exception):
    """Base class for all business rule exceptions in Axiom."""

    def __init__(self, message: str | Exception) -> None:
        self.message = str(message)
        super().__init__(self.message)


class ValidationException(DomainException):
    """Raised when a Value Object validation rule is violated."""


class InvalidStateTransition(DomainException):
    """Raised when attempting to change status illegally."""


class EntityNotFound(DomainException):
    """Raised when attempting to retrieve entity but no entity was found."""

    def __init__(self, entity_name: str, identifier: str):
        self.entity_name = entity_name
        self.identifier = identifier
        super().__init__(f"{entity_name} with identifier '{identifier}' was not found.")


class EntityAlreadyExists(DomainException):
    """Raised when attempting to create an entity that already exists."""

    def __init__(self, conflicting_field: str, identifier: str):
        self.conflicting_field = conflicting_field
        self.identifier = identifier
        super().__init__(f"The {conflicting_field} '{identifier}' is already taken.")


class InvalidValueError(DomainException):
    """Raised when an invalid value is provided for a specific domain concept."""

    def __init__(self, concept: str, invalid_value: str, valid_options: list[str] | None = None):
        msg = f"Invalid {concept}: '{invalid_value}'."
        if valid_options:
            msg += f" Valid options are: {', '.join(valid_options)}."
        super().__init__(msg)


class AmbiguousIdentifierError(ValidationException):
    """Exception raised when an identifier prefix matches multiple resources."""

    def __init__(self, resource_name: str, identifier: str, matches: list[str]):
        self.matches = matches
        msg: str = (
            f"Multiple {resource_name} found for prefix '{identifier}': "
            f"{', '.join(matches)}. Please provide a more specific ID prefix."
        )
        super().__init__(msg)


class InvalidIdentifierError(ValidationException):
    """Exception raised when an identifier format is invalid."""

    def __init__(self, identifier: str, details: str = ""):
        msg: str = f"The identifier '{identifier}' is malformed. {details}"
        super().__init__(msg)
