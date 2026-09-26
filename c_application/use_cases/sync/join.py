from uuid import UUID, uuid4

from a_core.exceptions import InvalidValueError
from b_domain.entities import User
from b_domain.exceptions.sync import AlreadyJoinedError
from b_domain.ports.password_hasher import PasswordHasher
from b_domain.ports.providers import ClockProvider
from b_domain.ports.sync_transport import DeviceAccess, SyncTransport
from b_domain.ports.use_case import UowFactoryType, UseCase
from b_domain.value_objects.identifiers import UserId
from b_domain.value_objects.sync import Hlc, SyncState
from c_application.dtos.sync_dtos import JoinSyncInputDTO, JoinSyncOutputDTO
from c_application.use_cases.context._common import load_user, parse_user_id


class JoinSyncUseCase(UseCase[JoinSyncInputDTO, JoinSyncOutputDTO]):
    """Join an account on a sync server, bringing everything the device has.

    With an invite, the account is created first — with the local user's ID,
    so the first device keeps its own. Then the device signs in and gets a
    token of its own. A device that joins an existing account becomes that
    account: its rows move to the account's ID. Every row the device has
    then waits to be pushed (the account's own row only on the first
    device: the next ones get it from the server), and the password typed
    becomes the local one too.
    """

    def __init__(
        self,
        uow_factory: UowFactoryType,
        clock: ClockProvider,
        transport: SyncTransport,
        hasher: PasswordHasher,
    ):
        super().__init__(uow_factory, clock)
        self.transport = transport
        self.hasher = hasher

    async def execute(self, request: JoinSyncInputDTO) -> JoinSyncOutputDTO:
        """Join.

        Raises:
            ValidationException: If the user ID is invalid.
            EntityNotFound: If the user does not exist.
            InvalidValueError: If the server is not an http(s) URL, or the
                device has no name.
            AlreadyJoinedError: If the device already syncs.
            SyncUnavailableError: If the server cannot be reached.
            SyncRefusedError: If the server refuses the invite or the
                username and password.
        """
        user_id: UserId = parse_user_id(request.user_id)
        server_url: str = _server_url(request.server_url)
        device_name: str = request.device_name.strip()
        if not device_name:
            raise InvalidValueError("device name", request.device_name)

        async with self.uow as uow:
            state: SyncState | None = await uow.sync.state()
            if state is not None:
                raise AlreadyJoinedError(state.server_url)
            user: User = await load_user(uow, user_id)
            email: str = user.email

        if request.invite is not None:
            await self.transport.create_account(
                server_url,
                invite=request.invite.strip(),
                account_id=user_id.value,
                username=request.username,
                email=email,
                password=request.password,
            )

        device_id: UUID = uuid4()
        access: DeviceAccess = await self.transport.register_device(
            server_url,
            username=request.username,
            password=request.password,
            device_id=device_id,
            device_name=device_name,
        )
        # Hashing is slow (bcrypt): outside the transaction
        password_hash: str = self.hasher.hash(request.password)

        account: UserId = UserId(access.account_id)
        async with self.uow as uow:
            if account != user_id:
                await uow.sync.adopt_account(user_id, account)
            user = await load_user(uow, account)
            user.change_password(password_hash, self.clock.now())
            await uow.users.update(user)

            clock: Hlc = Hlc.start(device_id).tick(self.clock.now())
            clock = await uow.sync.snapshot(
                clock, include_account=request.invite is not None
            )
            await uow.sync.save_state(
                SyncState(
                    server_url=server_url,
                    account_id=account.value,
                    device_id=device_id,
                    device_name=device_name,
                    clock=clock,
                )
            )
            pending: int = await uow.sync.count_pending()

        return JoinSyncOutputDTO(
            account_id=str(account),
            device_id=str(device_id),
            token=access.token,
            created_account=request.invite is not None,
            pending=pending,
        )


def _server_url(text: str) -> str:
    """The server's URL without a trailing slash.

    Raises:
        InvalidValueError: If it is not an http(s) URL.
    """
    url: str = text.strip().rstrip("/")
    scheme, _, rest = url.partition("://")
    if scheme.lower() not in ("http", "https") or not rest:
        raise InvalidValueError("server URL", text, ["https://…", "http://…"])
    return url
