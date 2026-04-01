from a_core.exceptions import EntityAlreadyExists, EntityNotFound


class UsernameAlreadyExistsError(EntityAlreadyExists):
    """Exception raised when a username is already in use."""

    def __init__(self, username: str):
        super().__init__(conflicting_field="username", identifier=username)


class EmailAlreadyExistsError(EntityAlreadyExists):
    """Exception raised when an email address is already registered."""

    def __init__(self, email: str):
        super().__init__(conflicting_field="email", identifier=email)


class UserNotFoundError(EntityNotFound):
    """Exception raised when a user does not exist."""

    def __init__(self, username: str):
        super().__init__(entity_name="User", identifier=username)
