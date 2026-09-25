from abc import ABC, abstractmethod

from b_domain.value_objects.identifiers import UserId
from b_domain.value_objects.user_behavior_metrics import UserBehaviorMetrics


class UserBehaviorMetricsRepository(ABC):
    """Contract for persistence operations on user behavior metrics.

    Defines methods for storing, retrieving, and deleting
    `UserBehaviorMetrics` associated with a given user.
    Implementations may use any storage backend (e.g., database, cache).
    """

    @abstractmethod
    async def save(self, metrics: UserBehaviorMetrics) -> UserBehaviorMetrics:
        """Persist metrics for a given user.

        Implementations must either create or update the stored metrics.

        Args:
            metrics (UserBehaviorMetrics): Aggregated metrics object to persist.
        """

    @abstractmethod
    async def get_by_user_id(self, user_id: UserId) -> UserBehaviorMetrics:
        """Retrieve metrics associated with a user.

        Args:
            user_id (UserId): Unique identifier of the user.

        Returns:
            Optional[UserBehaviorMetrics]: Metrics if present, otherwise None.
        """

    @abstractmethod
    async def delete(self, user_id: UserId) -> None:
        """Delete metrics associated with a user.

        Typically called when a user is removed from the system.

        Args:
            user_id (UserId): Unique identifier of the user.
        """
