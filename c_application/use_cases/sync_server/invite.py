from b_domain.value_objects.sync_server import (
    new_secret,
    secret_hash,
)
from c_application.dtos.sync_server_dtos import InviteOutputDTO
from c_application.use_cases.sync_server._common import SyncServerUseCase


class CreateInviteUseCase(SyncServerUseCase[None, InviteOutputDTO]):
    """A new invite, for the owner to hand to someone (for now, themself)."""

    async def execute(self, request: None = None) -> InviteOutputDTO:
        """Create it; the code is shown now and never again."""
        code: str = new_secret(12)
        await self.store.add_invite(secret_hash(code), self.clock.now())
        return InviteOutputDTO(code=code)
