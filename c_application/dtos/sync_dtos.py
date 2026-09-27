from dataclasses import dataclass, field

from a_core import DTO


@dataclass(frozen=True, kw_only=True)
class JoinSyncInputDTO(DTO):
    """Request to join a sync account on a server.

    Attributes:
        user_id (str): The local user, whose data goes up.
        server_url (str): The server (``https://…``).
        username (str): The account's username.
        password (str): The account's password (never kept; it also becomes
            the local one).
        device_name (str): What to call this device ("mint", "phone").
        invite (str | None): An invite code: creates the account (first
            device). None: signs in to an existing one.
    """

    user_id: str
    server_url: str
    username: str
    password: str = field(repr=False)
    device_name: str
    invite: str | None = None


@dataclass(frozen=True, kw_only=True)
class JoinSyncOutputDTO(DTO):
    """A device that joined.

    Attributes:
        account_id (str): The account (now the local user's ID too).
        device_id (str): This device.
        token (str): This device's token — the caller keeps it where only
            the owner reads it; every sync needs it.
        created_account (bool): Whether the account was created now.
        pending (int): Operations waiting for the first push.
    """

    account_id: str
    device_id: str
    token: str = field(repr=False)
    created_account: bool
    pending: int


@dataclass(frozen=True, kw_only=True)
class RunSyncInputDTO(DTO):
    """Request to sync now: push, then pull.

    Attributes:
        token (str): The device's token.
        batch (int): Operations per request.
    """

    token: str = field(repr=False)
    batch: int = 500


@dataclass(frozen=True, kw_only=True)
class RunSyncOutputDTO(DTO):
    """What a sync did.

    Attributes:
        pushed (int): Operations sent.
        pulled (int): Other devices' operations received.
        changed (int): Rows created, changed or deleted here.
        dropped (int): Operations that lost to a later change.
        pending (int): Operations still waiting (made meanwhile).
    """

    pushed: int
    pulled: int
    changed: int
    dropped: int
    pending: int


@dataclass(frozen=True, kw_only=True)
class SyncStatusOutputDTO(DTO):
    """Where the device stands.

    Attributes:
        joined (bool): Whether it syncs at all (the rest is empty if not).
        server_url (str | None): The server.
        account_id (str | None): The account.
        device_id (str | None): This device.
        device_name (str | None): Its name.
        pending (int): Operations waiting to be pushed.
        last_sync_at (str | None): When a sync last went through (ISO).
        last_error (str | None): Why the last one failed, if it did.
    """

    joined: bool
    server_url: str | None = None
    account_id: str | None = None
    device_id: str | None = None
    device_name: str | None = None
    pending: int = 0
    last_sync_at: str | None = None
    last_error: str | None = None


@dataclass(frozen=True, kw_only=True)
class SyncTokenInputDTO(DTO):
    """A request that only needs the device's token."""

    token: str = field(repr=False)


@dataclass(frozen=True, kw_only=True)
class RevokeSyncDeviceInputDTO(DTO):
    """Request to revoke another device.

    Attributes:
        token (str): This device's token.
        device (str): The other device's name or ID prefix.
    """

    token: str = field(repr=False)
    device: str


@dataclass(frozen=True, kw_only=True)
class SyncDeviceOutputDTO(DTO):
    """A device of the account.

    Attributes:
        device_id (str): Its ID.
        name (str): Its name.
        joined_at (str): When it joined (ISO).
        last_seen_at (str | None): When it last synced (ISO).
        revoked (bool): Whether it can no longer sync.
        this_device (bool): Whether it is the one asking.
    """

    device_id: str
    name: str
    joined_at: str
    last_seen_at: str | None
    revoked: bool
    this_device: bool


@dataclass(frozen=True, kw_only=True)
class SyncDevicesOutputDTO(DTO):
    """The account's devices, in the order they joined."""

    devices: list[SyncDeviceOutputDTO]
