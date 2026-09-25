from abc import ABC, abstractmethod

from b_domain.value_objects.identifiers import UserId
from b_domain.value_objects.user_behavior_profile import UserBehaviorProfile


class UserBehaviorProfileRepository(ABC):
    """Contract for persistence operations on user behavior profiles.

    Defines methods for storing, retrieving, and deleting
    `UserBehaviorProfile` objects associated with a given user.
    Implementations may use any storage backend (e.g., database, cache).
    """

    @abstractmethod
    async def save(self, profile: UserBehaviorProfile) -> None:
        """Persist a behavioral profile for a user.

        Implementations must either create or update the stored profile.

        Args:
            profile (UserBehaviorProfile): Behavioral profile object to persist.
        """

    @abstractmethod
    async def get_by_user_id(self, user_id: UserId) -> UserBehaviorProfile | None:
        """Retrieve the behavioral profile for a user.

        Args:
            user_id (UserId): Unique identifier of the user.

        Returns:
            Optional[UserBehaviorProfile]: Profile if found, otherwise None.
        """

    @abstractmethod
    async def delete(self, user_id: UserId) -> None:
        """Delete the behavioral profile associated with a user.

        Args:
            user_id (UserId): Unique identifier of the user.
        """
