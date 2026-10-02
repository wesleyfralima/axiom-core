from a_core import DomainException


class SyncException(DomainException):
    """Base exception for sync between devices."""


class NotJoinedError(SyncException):
    """This device has not joined an account on a server yet."""

    def __init__(self) -> None:
        super().__init__("This device does not sync yet: join a server first.")


class NotThisAccountError(SyncException):
    """The user asking is not the account this device syncs."""

    def __init__(self) -> None:
        super().__init__(
            "This device syncs another account: log in as that account to sync."
        )


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


class UpdateRequiredError(SyncRefusedError):
    """Another device of the account runs a newer series of the app: this
    one must be updated before it syncs (or changes anything) again. Every
    device of an account runs the same ``major.minor``; fixes may differ.

    Attributes:
        newest (str): The newest version among the account's devices.
        this (str | None): This device's version (None: too old to say).
    """

    def __init__(self, newest: str, this: str | None = None) -> None:
        self.newest = newest
        self.this = this
        super().__init__(
            f"Another device of this account runs Axiom Pro {newest}; this one "
            f"runs {this or 'an older version'}. Every device must run the "
            f"same version: update this one, then sync."
        )


class DeviceNotAllowedError(SyncRefusedError):
    """The server does not know the device's token, or it was revoked."""

    def __init__(self) -> None:
        super().__init__("This device is not allowed to sync: join again.")


class WrongCredentialsError(SyncRefusedError):
    """A wrong invite, username or password."""


class SyncConflictError(SyncRefusedError):
    """Something that must be unique already exists (a username, a device)."""
