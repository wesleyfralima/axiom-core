from a_core import DomainException


class SyncException(DomainException):
    """Base exception for sync between devices."""


class NotJoinedError(SyncException):
    """This device has not joined an account on a server yet."""

    def __init__(self) -> None:
        super().__init__("This device does not sync yet: join a server first.")


class AlreadyJoinedError(SyncException):
    """This device already syncs with an account."""

    def __init__(self, server_url: str) -> None:
        super().__init__(f"This device already syncs with {server_url}.")


class SyncUnavailableError(SyncException):
    """The server could not be reached, or did not answer in time. Nothing is
    lost: the changes wait for the next sync."""


class SyncRefusedError(SyncException):
    """The server said no: a wrong invite or password, a revoked device, a
    clock far ahead."""


class DeviceNotAllowedError(SyncRefusedError):
    """The server does not know the device's token, or it was revoked."""

    def __init__(self) -> None:
        super().__init__("This device is not allowed to sync: join again.")


class WrongCredentialsError(SyncRefusedError):
    """A wrong invite, username or password."""


class SyncConflictError(SyncRefusedError):
    """Something that must be unique already exists (a username, a device)."""
