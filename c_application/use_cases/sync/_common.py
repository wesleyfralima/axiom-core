from b_domain.exceptions.sync import NotJoinedError
from b_domain.ports.unit_of_work import UnitOfWork
from b_domain.value_objects.sync import SyncState


async def joined_state(uow: UnitOfWork) -> SyncState:
    """The device's sync state, which must exist.

    Raises:
        NotJoinedError: If the device has not joined an account.
    """
    state: SyncState | None = await uow.sync.state()
    if state is None:
        raise NotJoinedError()
    return state
