from b_domain.exceptions.sync import NotJoinedError, NotThisAccountError
from b_domain.ports.unit_of_work import UnitOfWork
from b_domain.value_objects import UserId
from b_domain.value_objects.sync import SyncState


async def joined_state(uow: UnitOfWork, user_id: str | None = None) -> SyncState:
    """The device's sync state, which must exist — and, when ``user_id`` is
    given, be that user's account (only its owner syncs a device).

    Raises:
        NotJoinedError: If the device has not joined an account.
        NotThisAccountError: If ``user_id`` is not the account it syncs.
        ValidationException: If ``user_id`` is not an ID.
    """
    state: SyncState | None = await uow.sync.state()
    if state is None:
        raise NotJoinedError()
    if (
        user_id is not None
        and UserId.from_string(user_id, error_msg="Invalid user ID.").value
        != state.account_id
    ):
        raise NotThisAccountError()
    return state
