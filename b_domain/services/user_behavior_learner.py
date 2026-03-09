from dataclasses import replace

from b_domain.value_objects.user_behavior_metrics import UserBehaviorMetrics
from b_domain.value_objects.user_behavior_profile import UserBehaviorProfile


class UserBehaviorLearner:
    """Updates the `UserBehaviorProfile` based on aggregated observed metrics.

    The learner adjusts long-term behavioral tendencies by considering:
        - Ratios of completed and skipped tasks
        - Average task duration and complexity
        - Fatigue and task abandonment patterns
        - Focus block lengths and intervals between tasks
        - Exploration noise adjustments over time
    """

    @staticmethod
    def learn(profile: UserBehaviorProfile, metrics: UserBehaviorMetrics) -> UserBehaviorProfile:
        """Update the user behavior profile based on aggregated metrics.

        Applies a learning rate to gradually adjust profile parameters
        such as ranking weights, fatigue, skip penalties, ultradian limits,
        momentum dynamics, and exploration noise. Ensures values remain
        within safe boundaries.

        Args:
            profile (UserBehaviorProfile): Current profile snapshot.
            metrics (UserBehaviorMetrics): Aggregated metrics observed from user behavior.

        Returns:
            UserBehaviorProfile: Updated profile with adjusted weights and limits.
        """

        # Learning rate: proportion of new data absorbed (0.0 to 1.0)
        lr: float = 0.2

        # -----------------------------------------------------
        # 1. Ranking weights (duration, complexity, energy)
        # -----------------------------------------------------
        new_w_duration: float = profile.w_duration + lr * (
                (metrics.avg_task_duration_minutes / profile.max_duration_score) - profile.w_duration
        )
        new_w_complexity: float = profile.w_complexity + lr * (
                (metrics.avg_task_complexity / profile.max_complexity_score) - profile.w_complexity
        )
        new_w_energy: float = profile.w_energy + lr * (
                (metrics.avg_energy_used / profile.max_energy_score) - profile.w_energy
        )

        # -----------------------------------------------------
        # 2. Fatigue and skip penalties
        # -----------------------------------------------------
        total_actions: int = metrics.total_tasks_completed + metrics.total_tasks_skipped
        skip_ratio: float = metrics.total_tasks_skipped / max(1, total_actions)  # avoid division by zero
        abandon_ratio: float = metrics.total_tasks_abandoned / max(1, total_actions)

        # More abandonments → increase fatigue weight
        new_energy_fatigue: float = profile.energy_fatigue_weight * (1.0 + abandon_ratio)

        # Skip penalty adjusted by proportion, capped at 0.5
        new_skip_penalty: float = profile.skip_penalty + skip_ratio * 0.5
        new_skip_penalty: float = min(new_skip_penalty, 0.5)

        # -----------------------------------------------------
        # 3. Cognitive limits (Ultradian rhythm)
        # -----------------------------------------------------
        new_ultradian: int = profile.ultradian_limit
        if metrics.avg_focus_block_minutes > 0:
            observed_limit = metrics.avg_focus_block_minutes * 1.2  # challenge margin
            new_ultradian = int(profile.ultradian_limit + lr * (observed_limit - profile.ultradian_limit))

        # -----------------------------------------------------
        # 4. Momentum dynamics
        # -----------------------------------------------------
        new_momentum_gap = profile.momentum_decay_gap_minutes
        if metrics.avg_completion_interval_minutes > 0:
            target_gap = metrics.avg_completion_interval_minutes * 1.5
            new_momentum_gap = int(
                profile.momentum_decay_gap_minutes + lr * (target_gap - profile.momentum_decay_gap_minutes)
            )

        # -----------------------------------------------------
        # 5. Exploration noise
        # -----------------------------------------------------
        # Less noise if more tasks are completed proportionally
        completion_ratio: float = metrics.total_tasks_completed / max(1, total_actions)
        new_noise: float = max(0.1, profile.exploration_noise * (0.5 + 0.5 * completion_ratio))

        # -----------------------------------------------------
        # 6. Return updated profile with safety limits
        # -----------------------------------------------------
        return replace(
            profile,
            w_duration=max(0.5, min(new_w_duration, 5.0)),
            w_complexity=max(0.5, min(new_w_complexity, 5.0)),
            w_energy=max(0.5, min(new_w_energy, 5.0)),
            energy_fatigue_weight=new_energy_fatigue,
            ultradian_limit=max(25, min(new_ultradian, 120)),
            momentum_decay_gap_minutes=max(10, min(new_momentum_gap, 60)),
            skip_penalty=new_skip_penalty,
            exploration_noise=new_noise
        )
