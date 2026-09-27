from dataclasses import dataclass, field
from typing import Any

from a_core import DTO


@dataclass(frozen=True, kw_only=True)
class InviteOutputDTO(DTO):
    """A new invite: its code is shown once and kept only as a hash."""

    code: str = field(repr=False)


@dataclass(frozen=True, kw_only=True)
class CreateSyncAccountInputDTO(DTO):
    """Request to create an account with an invite.

    Attributes:
        invite (str): The invite code.
        account_id (str): The account's ID (the first device's user ID).
        username (str): To sign devices in (3 to 32 letters, digits, ``._-``).
        email (str): The owner's e-mail.
        password (str): At least 8 characters.
    """

    invite: str = field(repr=False)
    account_id: str
    username: str
    email: str
    password: str = field(repr=False)


@dataclass(frozen=True, kw_only=True)
class SyncAccountOutputDTO(DTO):
    """An account that was created."""

    account_id: str
    username: str


@dataclass(frozen=True, kw_only=True)
class RegisterSyncDeviceInputDTO(DTO):
    """Request to sign a device in.

    Attributes:
        username (str): The account's username.
        password (str): Its password.
        device_id (str): The device's ID (it chooses it).
        device_name (str): What the owner calls it (up to 64 characters).
    """

    username: str
    password: str = field(repr=False)
    device_id: str
    device_name: str


@dataclass(frozen=True, kw_only=True)
class DeviceAccessOutputDTO(DTO):
    """A device signed in: its account and its token (shown once)."""

    account_id: str
    token: str = field(repr=False)


@dataclass(frozen=True, kw_only=True)
class PushInputDTO(DTO):
    """A device's operations (``SyncOperation.to_payload``)."""

    token: str = field(repr=False)
    operations: list[dict[str, Any]]


@dataclass(frozen=True, kw_only=True)
class PushOutputDTO(DTO):
    """What a push kept.

    Attributes:
        received (int): Operations sent.
        accepted (int): The new ones (the rest the server already had).
    """

    received: int
    accepted: int


@dataclass(frozen=True, kw_only=True)
class PullInputDTO(DTO):
    """A device asking for the account's operations after its cursor."""

    token: str = field(repr=False)
    after: int = 0
    limit: int = 500


@dataclass(frozen=True, kw_only=True)
class PullOutputDTO(DTO):
    """A page of the account's log.

    Attributes:
        operations (list[dict[str, Any]]): As payloads, in order.
        cursor (int): The last sequence in the page (or ``after``).
        more (bool): Whether there is more after it.
    """

    operations: list[dict[str, Any]]
    cursor: int
    more: bool


@dataclass(frozen=True, kw_only=True)
class ServerTokenInputDTO(DTO):
    """A request that only needs the device's token."""

    token: str = field(repr=False)


@dataclass(frozen=True, kw_only=True)
class RevokeServerDeviceInputDTO(DTO):
    """Request to revoke one of the account's devices."""

    token: str = field(repr=False)
    device_id: str


@dataclass(frozen=True, kw_only=True)
class ServerDeviceOutputDTO(DTO):
    """A device of the account, as the server knows it (ISO dates)."""

    device_id: str
    name: str
    joined_at: str
    last_seen_at: str | None
    revoked: bool
