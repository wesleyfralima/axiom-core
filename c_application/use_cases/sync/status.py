from a_core import DTO
from b_domain.ports.use_case import UseCase
from b_domain.value_objects.sync import SyncState
from c_application.dtos.sync_dtos import SyncStatusOutputDTO


class GetSyncStatusUseCase(UseCase[DTO | None, SyncStatusOutputDTO]):
    """Where the device stands: whether it syncs, with what, what waits, how
    the last sync went. Local only: no call to the server."""

    async def execute(self, request: DTO | None = None) -> SyncStatusOutputDTO:
        """Read the device's state."""
        async with self.uow as uow:
            state: SyncState | None = await uow.sync.state()
            if state is None:
                return SyncStatusOutputDTO(joined=False)
            pending: int = await uow.sync.count_pending()

        return SyncStatusOutputDTO(
            joined=True,
            server_url=state.server_url,
            account_id=str(state.account_id),
            device_id=str(state.device_id),
            device_name=state.device_name,
            pending=pending,
            last_sync_at=state.last_sync_at.isoformat() if state.last_sync_at else None,
            last_error=state.last_error,
        )
