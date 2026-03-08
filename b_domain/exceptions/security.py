from a_core import DomainException


class SecurityException(DomainException):
    """Base exception for all security and authentication errors."""

    def __init__(self, message: str = "A security error occurred."):
        super().__init__(message)


class NotAuthenticatedError(SecurityException):
    """Lançada quando uma operação exige utilizador autenticado, mas não há sessão."""

    def __init__(self, message: str = "User is not authenticated."):
        super().__init__(message)


class InvalidTokenError(SecurityException):
    """Token is malformed or signature does not match."""

    def __init__(self, message: str = "The provided token is invalid."):
        super().__init__(message)


class ExpiredTokenError(SecurityException):
    """Token is valid but has expired."""

    def __init__(self, message: str = "The provided token has expired."):
        super().__init__(message)
