from a_core.exceptions import ValidationException
from b_domain.value_objects.sync_server import SyncDevice
from c_application.dtos.sync_server_dtos import (
    PullInputDTO,
    PullOutputDTO,
)
from c_application.use_cases.sync_server._common import (
    MAX_BATCH,
    SyncServerUseCase,
)


class ServePullUseCase(SyncServerUseCase[PullInputDTO, PullOutputDTO]):
    """A page of the account's log after a device's cursor."""

    async def execute(self, request: PullInputDTO) -> PullOutputDTO:
        """Read it.

        Raises:
            DeviceNotAllowedError: If the token is unknown or revoked.
            ValidationException: If the cursor is negative.
        """
        device: SyncDevice = await self._device(request.token)
        if request.after < 0:
            raise ValidationException("The cursor cannot be negative.")
        limit: int = min(max(request.limit, 1), MAX_BATCH)
        page, more = await self.store.after(device.account_id, request.after, limit)
        await self.store.seen(device.device_id, self.clock.now())
        return PullOutputDTO(
            operations=[op.to_payload() for _, op in page],
            cursor=page[-1][0] if page else request.after,
            more=more,
        )
