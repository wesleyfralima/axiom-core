from datetime import datetime

from a_core.exceptions import ValidationException
from b_domain.value_objects.sync import SyncOperation
from b_domain.value_objects.sync_server import SyncDevice
from c_application.dtos.sync_server_dtos import (
    PushInputDTO,
    PushOutputDTO,
)
from c_application.use_cases.sync_server._common import (
    MAX_BATCH,
    MAX_CLOCK_AHEAD,
    SyncServerUseCase,
)


class AcceptPushUseCase(SyncServerUseCase[PushInputDTO, PushOutputDTO]):
    """Keep a device's operations in its account's log."""

    async def execute(self, request: PushInputDTO) -> PushOutputDTO:
        """Check and keep them.

        Raises:
            DeviceNotAllowedError: If the token is unknown or revoked.
            UpdateRequiredError: If another device of the account runs a
                newer series of the app.
            ValidationException: If there are too many operations, one is
                malformed, comes from another device, or has a clock too far
                ahead of the server's.
        """
        device: SyncDevice = await self._device(request.token)
        await self._same_version(device, request.app_version)
        if len(request.operations) > MAX_BATCH:
            raise ValidationException(
                f"A push takes up to {MAX_BATCH} operations "
                f"({len(request.operations)} came)."
            )
        now: datetime = self.clock.now()
        operations: list[SyncOperation] = []
        for payload in request.operations:
            op: SyncOperation = SyncOperation.from_payload(payload)
            if op.device_id != device.device_id.hex:
                raise ValidationException("An operation came from another device.")
            if op.hlc.is_ahead_of(now, MAX_CLOCK_AHEAD):
                raise ValidationException(
                    "This device's clock is more than a day ahead of the "
                    "server's: fix the date and time, then sync."
                )
            operations.append(op)

        accepted: int = await self.store.append(device.account_id, operations, now)
        return PushOutputDTO(received=len(operations), accepted=accepted)
