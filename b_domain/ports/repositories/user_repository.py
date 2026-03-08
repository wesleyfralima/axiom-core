from abc import abstractmethod, ABC
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from b_domain.entities import User
    from b_domain.ports.repositories.filters import UserFilter
    from b_domain.value_objects.identifiers import UserId


class UserRepository(ABC):
    """Contract for User persistence operations.

    Any database adapter must implement these methods to be injected
    via the UnitOfWork.
    """

    @abstractmethod
    async def add(self, user: "User") -> None:
        """Add a new user.

        Args:
            user (User): The domain user entity to be added.
        """

    @abstractmethod
    async def update(self, user: "User") -> None:
        """Update an existing user.

        This method persists any changes made to the user entity,
        including password changes and preference updates.

        Args:
            user (User): The user entity with updated values.
        """

    @abstractmethod
    async def delete(self, user_id: "UserId") -> None:
        """Permanently remove a user.

        Args:
            user_id (UserId): The ID of the user to delete.
        """

    @abstractmethod
    async def get_by_id(self, user_id: "UserId") -> Optional["User"]:
        """Retrieve a user by their unique ID.

        Args:
            user_id (UserId): The user's unique identifier.

        Returns:
            Optional[User]: The instantiated domain user if found, otherwise None.
        """

    @abstractmethod
    async def get_by_username(self, username: str) -> Optional["User"]:
        """Retrieve a user by their username.

        Args:
            username (str): The unique username string.

        Returns:
            Optional[User]: The user entity if found, otherwise None.
        """

    @abstractmethod
    async def list(self, filters: "UserFilter") -> List["User"]:
        """Return a paginated list of users based on provided filters.

        The implementation MUST respect the `limit` and `offset` attributes
        present in the BaseFilter.

        Args:
            filters (UserFilter): The filter criteria, including pagination.

        Returns:
            List[User]: A list of user entities matching the filters.
        """

    @abstractmethod
    async def count(self, filters: "UserFilter") -> int:
        """Return the total count of users matching the filters.

        The implementation MUST ignore the `limit` and `offset` attributes
        when counting, returning the total absolute number of matching rows.

        Args:
            filters (UserFilter): The filter criteria.

        Returns:
            int: Total number of users matching the filters.
        """
