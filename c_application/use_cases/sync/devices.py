from __future__ import annotations

from a_core import EntityNotFound
from a_core.exceptions import AmbiguousIdentifierError, InvalidValueError
from a_core.text import fold
from b_domain.ports.providers import ClockProvider
from b_domain.ports.sync_transport import DeviceInfo, SyncTransport
from b_domain.ports.use_case import UowFactoryType, UseCase
from b_domain.value_objects.sync import SyncState
from c_application.dtos.sync_dtos import (
    RevokeSyncDeviceInputDTO,
    SyncDeviceOutputDTO,
    SyncDevicesOutputDTO,
    SyncTokenInputDTO,
)
from c_application.use_cases.sync._common import joined_state


class _DevicesUseCase[TReq, TResp](UseCase[TReq, TResp]):
    """A use case that asks the server about the account's devices."""

    def __init__(
        self,
        uow_factory: UowFactoryType,
        clock: ClockProvider,
        transport: SyncTransport,
    ):
        super().__init__(uow_factory, clock)
        self.transport = transport

    async def _devices(
        self, user_id: str, token: str
    ) -> tuple[SyncState, list[DeviceInfo]]:
        async with self.uow as uow:
            state: SyncState = await joined_state(uow, user_id)
        return state, await self.transport.devices(state.server_url, token)


class ListSyncDevicesUseCase(_DevicesUseCase[SyncTokenInputDTO, SyncDevicesOutputDTO]):
    """The account's devices, this one marked."""

    async def execute(self, request: SyncTokenInputDTO) -> SyncDevicesOutputDTO:
        """Ask the server.

        Raises:
            NotJoinedError: If the device does not sync.
            NotThisAccountError: If the user is not the account it syncs.
            SyncUnavailableError: If the server cannot be reached.
            SyncRefusedError: If the server refuses the device.
        """
        state, devices = await self._devices(request.user_id, request.token)
        return SyncDevicesOutputDTO(devices=[_output(d, state) for d in devices])


class RevokeSyncDeviceUseCase(
    _DevicesUseCase[RevokeSyncDeviceInputDTO, SyncDeviceOutputDTO]
):
    """Revoke another device (a lost phone): it can no longer sync. Its data
    stays on it, and what it pushed stays in the account."""

    async def execute(self, request: RevokeSyncDeviceInputDTO) -> SyncDeviceOutputDTO:
        """Find the device by name or ID prefix and revoke it.

        Raises:
            NotJoinedError: If the device does not sync.
            NotThisAccountError: If the user is not the account it syncs.
            EntityNotFound: If no device matches.
            AmbiguousIdentifierError: If several do.
            InvalidValueError: If it is this device.
            SyncUnavailableError: If the server cannot be reached.
            SyncRefusedError: If the server refuses.
        """
        state, devices = await self._devices(request.user_id, request.token)
        wanted: str = fold(request.device.strip())
        hex_prefix: str = wanted.replace("-", "")
        matches: list[DeviceInfo] = [d for d in devices if fold(d.name) == wanted] or [
            d
            for d in devices
            if len(hex_prefix) >= 4 and d.device_id.hex.startswith(hex_prefix)
        ]
        if not matches:
            raise EntityNotFound(entity_name="Device", identifier=request.device)
        if len(matches) > 1:
            raise AmbiguousIdentifierError(
                "devices", request.device, [str(d.device_id) for d in matches]
            )
        device: DeviceInfo = matches[0]
        if device.device_id == state.device_id:
            raise InvalidValueError(
                "device to revoke", request.device, ["another device of the account"]
            )
        await self.transport.revoke_device(
            state.server_url, request.token, device.device_id
        )
        return _output(
            DeviceInfo(
                device_id=device.device_id,
                name=device.name,
                joined_at=device.joined_at,
                last_seen_at=device.last_seen_at,
                revoked=True,
                app_version=device.app_version,
            ),
            state,
        )


def _output(device: DeviceInfo, state: SyncState) -> SyncDeviceOutputDTO:
    return SyncDeviceOutputDTO(
        device_id=str(device.device_id),
        name=device.name,
        joined_at=device.joined_at.isoformat(),
        last_seen_at=device.last_seen_at.isoformat() if device.last_seen_at else None,
        revoked=device.revoked,
        this_device=device.device_id == state.device_id,
        app_version=device.app_version,
    )
