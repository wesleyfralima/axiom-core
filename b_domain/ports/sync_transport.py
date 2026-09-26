"""How a device talks to the sync server."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from b_domain.value_objects.sync import SyncOperation


@dataclass(frozen=True, kw_only=True)
class DeviceAccess:
    """What the server gives a device that joins.

    Attributes:
        account_id (UUID): The account.
        token (str): The device's own token — long-lived, revocable. The
            caller keeps it somewhere only the owner reads.
    """

    account_id: UUID
    token: str


@dataclass(frozen=True, kw_only=True)
class PullPage:
    """A page of other devices' operations.

    Attributes:
        operations (list[SyncOperation]): In the server's order.
        cursor (int): The sequence of the last one, to pull after next time.
        more (bool): Whether there is more after this page.
    """

    operations: list[SyncOperation]
    cursor: int
    more: bool


@dataclass(frozen=True, kw_only=True)
class DeviceInfo:
    """A device of the account, as the server knows it."""

    device_id: UUID
    name: str
    joined_at: datetime
    last_seen_at: datetime | None
    revoked: bool


class SyncTransport(ABC):
    """The sync server's calls.

    Every call raises ``SyncUnavailableError`` when the server cannot be
    reached in time, and ``SyncRefusedError`` when it says no.
    """

    @abstractmethod
    async def create_account(
        self,
        server_url: str,
        *,
        invite: str,
        account_id: UUID,
        username: str,
        email: str,
        password: str,
    ) -> None:
        """Create the account an invite allows, with the given ID (the first
        device's user keeps its own)."""

    @abstractmethod
    async def register_device(
        self,
        server_url: str,
        *,
        username: str,
        password: str,
        device_id: UUID,
        device_name: str,
    ) -> DeviceAccess:
        """Sign a device in to the account; it gets its own token."""

    @abstractmethod
    async def push(
        self, server_url: str, token: str, operations: Sequence[SyncOperation]
    ) -> None:
        """Send operations; the ones the server already has are ignored."""

    @abstractmethod
    async def pull(
        self, server_url: str, token: str, after: int, limit: int
    ) -> PullPage:
        """The account's operations after the sequence ``after``."""

    @abstractmethod
    async def devices(self, server_url: str, token: str) -> list[DeviceInfo]:
        """The account's devices."""

    @abstractmethod
    async def revoke_device(self, server_url: str, token: str, device_id: UUID) -> None:
        """Revoke a device's token: it cannot sync any more."""
