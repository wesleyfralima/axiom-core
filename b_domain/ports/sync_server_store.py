"""What the sync server keeps: invites, accounts, devices and the log."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from b_domain.value_objects.sync import SyncOperation
from b_domain.value_objects.sync_server import SyncAccount, SyncDevice


class SyncServerStore(ABC):
    """The server's storage. Each call is a transaction of its own.

    The log is one sequence for the whole server, increasing: an account's
    operations, in the order they arrived, are the ones with its ID — a
    device's cursor is the last sequence it pulled.
    """

    @abstractmethod
    async def add_invite(self, code_hash: str, now: datetime) -> None:
        """Keep a new invite (its code, hashed)."""

    @abstractmethod
    async def invite_is_open(self, code_hash: str) -> bool:
        """Whether an invite exists and was not used."""

    @abstractmethod
    async def create_account(self, account: SyncAccount, invite_hash: str) -> bool:
        """Create an account and use up its invite, together.

        Returns:
            bool: False when the invite was used meanwhile (nothing is
            created).
        """

    @abstractmethod
    async def account_by_username(self, username: str) -> SyncAccount | None:
        """The account with this username (ignoring case)."""

    @abstractmethod
    async def account_exists(self, account_id: UUID) -> bool:
        """Whether an account has this ID."""

    @abstractmethod
    async def add_device(self, device: SyncDevice) -> None:
        """Keep a new device."""

    @abstractmethod
    async def device(self, device_id: UUID) -> SyncDevice | None:
        """The device with this ID."""

    @abstractmethod
    async def device_by_token(self, token_hash: str) -> SyncDevice | None:
        """The device whose token has this hash."""

    @abstractmethod
    async def devices(self, account_id: UUID) -> list[SyncDevice]:
        """The account's devices, in the order they joined."""

    @abstractmethod
    async def revoke_device(self, device_id: UUID, now: datetime) -> None:
        """Revoke a device's token."""

    @abstractmethod
    async def seen(self, device_id: UUID, now: datetime) -> None:
        """Note that a device synced now."""

    @abstractmethod
    async def append(
        self, account_id: UUID, operations: Sequence[SyncOperation], now: datetime
    ) -> int:
        """Add operations to the account's log, ignoring the ones it already
        has (by ``op_id``).

        Returns:
            int: How many were new.
        """

    @abstractmethod
    async def after(
        self, account_id: UUID, sequence: int, limit: int
    ) -> tuple[list[tuple[int, SyncOperation]], bool]:
        """The account's operations after ``sequence``, up to ``limit``.

        Returns:
            tuple: ``(sequence, operation)`` pairs in order, and whether there
            is more after them.
        """
