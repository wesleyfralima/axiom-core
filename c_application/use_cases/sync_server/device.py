from uuid import UUID

from a_core.exceptions import ValidationException
from b_domain.exceptions.sync import (
    SyncConflictError,
    WrongCredentialsError,
)
from b_domain.ports.password_hasher import PasswordHasher
from b_domain.ports.providers import ClockProvider
from b_domain.ports.sync_server_store import SyncServerStore
from b_domain.value_objects.sync_server import (
    SyncAccount,
    SyncDevice,
    new_secret,
    secret_hash,
)
from c_application.dtos.sync_server_dtos import (
    DeviceAccessOutputDTO,
    RegisterSyncDeviceInputDTO,
)
from c_application.use_cases.sync_server._common import (
    SyncServerUseCase,
    parse_uuid,
)


class RegisterSyncDeviceUseCase(
    SyncServerUseCase[RegisterSyncDeviceInputDTO, DeviceAccessOutputDTO]
):
    """Sign a device in with the account's username and password: it gets a
    token of its own, which it keeps."""

    def __init__(
        self, store: SyncServerStore, clock: ClockProvider, hasher: PasswordHasher
    ):
        super().__init__(store, clock)
        self.hasher = hasher

    async def execute(
        self, request: RegisterSyncDeviceInputDTO
    ) -> DeviceAccessOutputDTO:
        """Sign it in.

        Raises:
            ValidationException: If the device ID or name is not valid.
            WrongCredentialsError: If the username or password is wrong.
            SyncConflictError: If the device ID is taken.
        """
        device_id: UUID = parse_uuid(request.device_id, "device ID")
        name: str = request.device_name.strip()
        if not 1 <= len(name) <= 64:
            raise ValidationException("A device name has 1 to 64 characters.")

        account: SyncAccount | None = await self.store.account_by_username(
            request.username.strip()
        )
        if account is None or not self.hasher.verify(
            request.password, account.password_hash
        ):
            raise WrongCredentialsError("Wrong username or password.")
        if await self.store.device(device_id) is not None:
            raise SyncConflictError("A device with this ID already exists.")

        token: str = new_secret()
        await self.store.add_device(
            SyncDevice(
                device_id=device_id,
                account_id=account.account_id,
                name=name,
                token_hash=secret_hash(token),
                joined_at=self.clock.now(),
            )
        )
        return DeviceAccessOutputDTO(account_id=str(account.account_id), token=token)
