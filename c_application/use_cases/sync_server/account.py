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
    secret_hash,
)
from c_application.dtos.sync_server_dtos import (
    CreateSyncAccountInputDTO,
    SyncAccountOutputDTO,
)
from c_application.use_cases.sync_server._common import (
    MIN_PASSWORD,
    USERNAME,
    SyncServerUseCase,
    parse_uuid,
)


class CreateSyncAccountUseCase(
    SyncServerUseCase[CreateSyncAccountInputDTO, SyncAccountOutputDTO]
):
    """Create an account with an invite, which it uses up."""

    def __init__(
        self, store: SyncServerStore, clock: ClockProvider, hasher: PasswordHasher
    ):
        super().__init__(store, clock)
        self.hasher = hasher

    async def execute(self, request: CreateSyncAccountInputDTO) -> SyncAccountOutputDTO:
        """Create it.

        Raises:
            ValidationException: If a field is not valid.
            WrongCredentialsError: If the invite is unknown or used.
            SyncConflictError: If the username or the ID is taken.
        """
        account_id: UUID = parse_uuid(request.account_id, "account ID")
        username: str = request.username.strip()
        if not USERNAME.fullmatch(username):
            raise ValidationException(
                "A username has 3 to 32 letters, digits, dots, dashes or underscores."
            )
        if "@" not in request.email:
            raise ValidationException("That is not an e-mail address.")
        if len(request.password) < MIN_PASSWORD:
            raise ValidationException(
                f"A password has at least {MIN_PASSWORD} characters."
            )

        invite: str = secret_hash(request.invite)
        if not await self.store.invite_is_open(invite):
            raise WrongCredentialsError("This invite is unknown or already used.")
        if await self.store.account_by_username(username) is not None:
            raise SyncConflictError(f"The username {username!r} is taken.")
        if await self.store.account_exists(account_id):
            raise SyncConflictError("An account with this ID already exists.")

        created: bool = await self.store.create_account(
            SyncAccount(
                account_id=account_id,
                username=username,
                email=request.email.strip(),
                password_hash=self.hasher.hash(request.password),
                created_at=self.clock.now(),
            ),
            invite,
        )
        if not created:
            raise WrongCredentialsError("This invite is unknown or already used.")
        return SyncAccountOutputDTO(account_id=str(account_id), username=username)
