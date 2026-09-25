from a_core import DomainException


class SecurityException(DomainException):
    """Base exception for all security and authentication errors."""

    def __init__(self, message: str = "A security error occurred."):
        super().__init__(message)


class NotAuthenticatedError(SecurityException):
    """
    Exception raised when an operation requires
    authentication but no active session exists.
    """

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


class InvalidCredentialsError(SecurityException):
    """Exception raised when login credentials are invalid."""

    def __init__(self, message: str = "Invalid username or password."):
        super().__init__(message)


class SessionRevocationError(SecurityException):
    """Exception raised when session revocation fails."""

    def __init__(
        self, message: str = "Could not revoke session. It might be already inactive."
    ):
        super().__init__(message)


class AccountLockedError(SecurityException):
    """Exception raised when an account is temporarily locked."""

    def __init__(
        self,
        message: str = "Account is temporarily locked due to multiple failed attempts.",
    ):
        super().__init__(message)


class WeakPasswordError(SecurityException):
    """Exception raised when a password does not meet complexity requirements."""

    def __init__(self, reason: str = "Password does not meet security requirements."):
        super().__init__(reason)
