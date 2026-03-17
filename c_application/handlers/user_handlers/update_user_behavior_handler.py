from b_domain.events.task_events import TaskCompletedEvent
from b_domain.ports.unity_of_work import UnitOfWork
from b_domain.services.user_behavior_learner import UserBehaviorLearner
from b_domain.services.user_behavior_metrics_aggregator import UserBehaviorMetricsAggregator
from b_domain.value_objects.user_behavior_metrics import UserBehaviorMetrics
from b_domain.value_objects.user_behavior_profile import UserBehaviorProfile


class UpdateUserBehaviorHandler:
    """Domain event handler that updates user behavior metrics and profile.

    Reacts to task completion events by:
      1. Aggregating new behavioral metrics.
      2. Updating the user’s behavior profile via learning heuristics/AI.
      3. Persisting both metrics and profile for future recommendations.
    """

    def __init__(
            self,
            uow: UnitOfWork,
            aggregator: UserBehaviorMetricsAggregator,
            learner: UserBehaviorLearner,
    ):
        """Initialize the handler.

        Args:
            uow (UnitOfWork): Unit of Work for transactional consistency.
            aggregator (UserBehaviorMetricsAggregator): Service for aggregating metrics.
            learner (UserBehaviorLearner): Service for updating user behavior profile.
        """
        self.uow = uow
        self.aggregator = aggregator
        self.learner = learner

    async def handle(self, event: TaskCompletedEvent) -> None:
        """Handle a TaskCompletedEvent.

        Steps:
            1. Load current metrics and profile for the user.
            2. Aggregate new metrics based on the completed task.
            3. Update the user’s profile using the learner service.
            4. Persist updated metrics and profile.

        Args:
            event (TaskCompletedEvent): The domain event signaling task completion.
        """

        metrics: UserBehaviorMetrics | None
        profile: UserBehaviorProfile | None
        new_metrics: UserBehaviorMetrics
        new_profile: UserBehaviorProfile

        async with self.uow:

            # Load current state (metrics and profile)
            metrics = await self.uow.user_behavior_metrics.get_by_user_id(event.user_id)
            if metrics is None:
                metrics = UserBehaviorMetrics(user_id=event.user_id)

            profile = await self.uow.user_behavior_profiles.get_by_user_id(event.user_id)
            if profile is None:
                profile = UserBehaviorProfile(user_id=event.user_id)

            # 1. Aggregate new completion into historical metrics
            new_metrics = self.aggregator.record_task_completed(
                metrics=metrics,
                duration_minutes=event.actual_minutes,
                energy=event.energy_level_used,
                complexity=event.task_complexity,
                now=event.occurred_at,
            )

            # 2. Update profile using learner (heuristics/AI)
            new_profile = self.learner.learn(
                profile=profile,
                metrics=new_metrics,
            )

            # 3. Persist both updated metrics and profile
            await self.uow.user_behavior_metrics.save(new_metrics)
            await self.uow.user_behavior_profiles.save(new_profile)
