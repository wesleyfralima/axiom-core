from dataclasses import replace

from b_domain.exceptions.sync import SyncException
from b_domain.ports.providers import ClockProvider
from b_domain.ports.sync_transport import PullPage, SyncTransport
from b_domain.ports.use_case import UowFactoryType, UseCase
from b_domain.services.sync_merge import MergePlan, plan_merge
from b_domain.value_objects.sync import Hlc, SyncOperation, SyncState
from c_application.dtos.sync_dtos import RunSyncInputDTO, RunSyncOutputDTO
from c_application.use_cases.sync._common import joined_state


class RunSyncUseCase(UseCase[RunSyncInputDTO, RunSyncOutputDTO]):
    """Sync now: push what this device changed, then pull the others'.

    The network calls run outside any transaction; each batch pushed is
    forgotten, and each page pulled is applied with the cursor, in one
    transaction — a sync cut in half goes on where it stopped. A failure is
    kept in the state (``sync status`` shows it) and raised.
    """

    def __init__(
        self,
        uow_factory: UowFactoryType,
        clock: ClockProvider,
        transport: SyncTransport,
    ):
        super().__init__(uow_factory, clock)
        self.transport = transport

    async def execute(self, request: RunSyncInputDTO) -> RunSyncOutputDTO:
        """Push, then pull.

        Raises:
            NotJoinedError: If the device does not sync.
            NotThisAccountError: If the user is not the account it syncs.
            SyncUnavailableError: If the server cannot be reached.
            SyncRefusedError: If the server refuses the device.
        """
        async with self.uow as uow:
            state: SyncState = await joined_state(uow, request.user_id)

        try:
            pushed: int = await self._push(state.server_url, request)
            pulled, changed, dropped = await self._pull(state.server_url, request)
        except SyncException as e:
            async with self.uow as uow:
                failed: SyncState = await joined_state(uow)
                await uow.sync.save_state(replace(failed, last_error=str(e)))
            raise

        async with self.uow as uow:
            done: SyncState = await joined_state(uow)
            await uow.sync.save_state(
                replace(done, last_sync_at=self.clock.now(), last_error=None)
            )
            pending: int = await uow.sync.count_pending()

        return RunSyncOutputDTO(
            pushed=pushed,
            pulled=pulled,
            changed=changed,
            dropped=dropped,
            pending=pending,
        )

    async def _push(self, server_url: str, request: RunSyncInputDTO) -> int:
        """Send the waiting operations, a batch at a time; how many went."""
        pushed: int = 0
        while True:
            async with self.uow as uow:
                batch: list[SyncOperation] = await uow.sync.pending(request.batch)
            if not batch:
                return pushed
            await self.transport.push(server_url, request.token, batch)
            async with self.uow as uow:
                await uow.sync.forget([op.op_id for op in batch])
            pushed += len(batch)
            if len(batch) < request.batch:
                return pushed

    async def _pull(
        self, server_url: str, request: RunSyncInputDTO
    ) -> tuple[int, int, int]:
        """Apply the other devices' operations, a page at a time; how many
        came, how many rows changed, how many were dropped."""
        pulled = changed = dropped = 0
        while True:
            async with self.uow as uow:
                cursor: int = (await joined_state(uow)).cursor
            page: PullPage = await self.transport.pull(
                server_url, request.token, cursor, request.batch
            )
            async with self.uow as uow:
                state: SyncState = await joined_state(uow)
                # Our own operations come back too: they change nothing
                theirs: list[SyncOperation] = [
                    op for op in page.operations if op.device_id != state.device_id.hex
                ]
                plan: MergePlan = plan_merge(theirs, await uow.sync.clocks(theirs))
                await uow.sync.apply(plan)
                clock: Hlc = (
                    state.clock.receive(plan.latest, self.clock.now())
                    if plan.latest is not None
                    else state.clock
                )
                await uow.sync.save_state(
                    replace(state, clock=clock, cursor=page.cursor)
                )
            pulled += len(theirs)
            changed += len(plan.rows)
            dropped += len(plan.dropped)
            if not page.more:
                return pulled, changed, dropped
