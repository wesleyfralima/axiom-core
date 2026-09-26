"""The device's side of sync, inside the unit of work."""

from abc import ABC, abstractmethod
from collections.abc import Collection, Iterable
from uuid import UUID

from b_domain.services.sync_merge import MergePlan
from b_domain.value_objects.identifiers import UserId
from b_domain.value_objects.sync import FieldKey, Hlc, SyncOperation, SyncState


class SyncStore(ABC):
    """What a device keeps to sync: its state, the operations waiting to go
    up, and the clock of every field it holds.

    Once the device has joined, every change a unit of work saves also
    becomes operations here, in the same transaction — the implementation
    records them on its own, so no use case has to.
    """

    @abstractmethod
    async def state(self) -> SyncState | None:
        """The device's state; None before it joins."""

    @abstractmethod
    async def save_state(self, state: SyncState) -> None:
        """Keep the device's state."""

    @abstractmethod
    async def pending(self, limit: int) -> list[SyncOperation]:
        """The oldest operations not yet pushed, up to ``limit``."""

    @abstractmethod
    async def count_pending(self) -> int:
        """How many operations wait to be pushed."""

    @abstractmethod
    async def forget(self, op_ids: Collection[UUID]) -> None:
        """Drop operations the server has (their ``op_id``)."""

    @abstractmethod
    async def clocks(self, operations: Iterable[SyncOperation]) -> dict[FieldKey, Hlc]:
        """The clocks kept for the rows these operations touch (every field
        of each row, ``CREATED`` and ``DELETED`` included)."""

    @abstractmethod
    async def apply(self, plan: MergePlan) -> None:
        """Apply other devices' changes straight to the data and keep the
        plan's clocks. Nothing here becomes an operation to push — except
        what the device must fix on its own (two contexts with one name),
        which it records as its own change."""

    @abstractmethod
    async def snapshot(self, clock: Hlc, include_account: bool) -> Hlc:
        """Turn every row the device has into a new-row operation (and keep
        their clocks), for its first push.

        Args:
            clock (Hlc): The device's clock before the first operation.
            include_account (bool): Also the account's own row (username,
                e-mail, preferences) — only on the device that creates the
                account; a device joining an existing one gets it from the
                server.

        Returns:
            Hlc: The clock after the last operation.
        """

    @abstractmethod
    async def adopt_account(self, local: UserId, account: UserId) -> None:
        """Make the local user the account: every row of ``local`` moves to
        ``account``'s ID."""
