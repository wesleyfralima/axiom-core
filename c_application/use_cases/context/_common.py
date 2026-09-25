from a_core import EntityNotFound
from b_domain.entities import User
from b_domain.ports.unit_of_work import UnitOfWork
from b_domain.value_objects import UserId


def parse_user_id(user_id: str) -> UserId:
    """Parse the requester's ID, failing with a clear message."""
    return UserId.from_string(user_id, error_msg="Invalid user ID.")


async def load_user(uow: UnitOfWork, user_id: UserId) -> User:
    """Fetch the requester, who must exist.

    Raises:
        EntityNotFound: If there is no such user.
    """
    user: User | None = await uow.users.get_by_id(user_id)
    if not user:
        raise EntityNotFound(entity_name="User", identifier=str(user_id))
    return user
