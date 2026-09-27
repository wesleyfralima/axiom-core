from datetime import datetime
from uuid import UUID

from a_core import EntityNotFound
from b_domain.value_objects.sync_server import SyncDevice
from c_application.dtos.sync_server_dtos import (
    RevokeServerDeviceInputDTO,
    ServerDeviceOutputDTO,
    ServerTokenInputDTO,
)
from c_application.use_cases.sync_server._common import (
    SyncServerUseCase,
    device_output,
    parse_uuid,
)


class ListServerDevicesUseCase(
    SyncServerUseCase[ServerTokenInputDTO, list[ServerDeviceOutputDTO]]
):
    """The account's devices."""

    async def execute(
        self, request: ServerTokenInputDTO
    ) -> list[ServerDeviceOutputDTO]:
        """List them.

        Raises:
            DeviceNotAllowedError: If the token is unknown or revoked.
        """
        device: SyncDevice = await self._device(request.token)
        return [device_output(d) for d in await self.store.devices(device.account_id)]


class RevokeServerDeviceUseCase(
    SyncServerUseCase[RevokeServerDeviceInputDTO, ServerDeviceOutputDTO]
):
    """Revoke one of the account's devices (a lost phone)."""

    async def execute(
        self, request: RevokeServerDeviceInputDTO
    ) -> ServerDeviceOutputDTO:
        """Revoke it.

        Raises:
            DeviceNotAllowedError: If the token is unknown or revoked.
            ValidationException: If the ID is not valid.
            EntityNotFound: If the account has no such device.
        """
        me: SyncDevice = await self._device(request.token)
        device_id: UUID = parse_uuid(request.device_id, "device ID")
        target: SyncDevice | None = await self.store.device(device_id)
        if target is None or target.account_id != me.account_id:
            raise EntityNotFound(entity_name="Device", identifier=request.device_id)
        now: datetime = self.clock.now()
        if target.revoked_at is None:
            await self.store.revoke_device(device_id, now)
        return device_output(
            SyncDevice(
                device_id=target.device_id,
                account_id=target.account_id,
                name=target.name,
                token_hash=target.token_hash,
                joined_at=target.joined_at,
                last_seen_at=target.last_seen_at,
                revoked_at=target.revoked_at or now,
            )
        )
