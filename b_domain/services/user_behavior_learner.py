from dataclasses import replace
from typing import Any

from b_domain.value_objects.user_behavior_metrics import UserBehaviorMetrics
from b_domain.value_objects.user_behavior_profile import UserBehaviorProfile


class UserBehaviorLearner:
    """Learns and updates long-term behavioral tendencies from aggregated metrics.

    This class adjusts the `UserBehaviorProfile` by applying incremental learning
    rules with a defined learning rate. It considers multiple behavioral factors:

    - Ranking weights: duration, complexity, and energy usage
    - Fatigue and skip behavior: penalties and abandonment ratios
    - Cognitive limits: focus cycles and ultradian rhythms
    - Momentum dynamics: intervals between task completions
    - Exploration: noise reduction as experience grows
    - Preferences: alignment with observed averages
    - Sustainable capacity: maximum tolerable duration and complexity
    - Pause behavior: average rest and recovery patterns
    """

    LEARNING_RATE: float = 0.2
    RANKING_SCALE: int = 6

    @classmethod
    def learn(
        cls,
        profile: UserBehaviorProfile,
        metrics: UserBehaviorMetrics,
    ) -> UserBehaviorProfile:
        """Update the user behavior profile based on aggregated metrics.

        Applies a learning rate to gradually adjust profile parameters
        such as ranking weights, fatigue, skip penalties, ultradian limits,
        momentum dynamics, and exploration noise. Ensures values remain
        within safe boundaries.

        Args:
            profile (UserBehaviorProfile): Current profile snapshot.
            metrics (UserBehaviorMetrics): Aggregated metrics
                observed from user behavior.

        Returns:
            UserBehaviorProfile: Updated profile with adjusted weights and limits.
        """

        lr: float = cls.LEARNING_RATE

        weights = cls._learn_ranking_weights(profile, metrics, lr)
        fatigue = cls._learn_fatigue_and_skip(profile, metrics, lr)
        cognitive = cls._learn_cognitive_limits(profile, metrics, lr)
        momentum = cls._learn_momentum(profile, metrics, lr)
        exploration = cls._learn_exploration(profile, metrics)
        preferences = cls._learn_preferences(profile, metrics, lr)
        capacity = cls._learn_capacity(profile, metrics)
        pauses = cls._learn_pause_patterns(profile, metrics, lr)

        changes: dict[str, Any] = {
            **weights,
            **fatigue,
            **cognitive,
            **momentum,
            **exploration,
            **preferences,
            **capacity,
            **pauses,
        }

        return replace(profile, **changes)

    # -----------------------------------------------------
    # Ranking weights
    # -----------------------------------------------------

    @classmethod
    def _learn_ranking_weights(
        cls,
        profile: UserBehaviorProfile,
        metrics: UserBehaviorMetrics,
        lr: float,
    ) -> dict[str, float]:
        """Adjust ranking weights for duration, complexity, and energy."""

        w_duration: float = profile.w_duration + lr * (
            (metrics.avg_task_duration_minutes / profile.max_duration_score)
            - profile.w_duration
        )
        w_complexity: float = profile.w_complexity + lr * (
            (metrics.avg_task_complexity / profile.max_complexity_score)
            - profile.w_complexity
        )
        w_energy: float = profile.w_energy + lr * (
            (metrics.avg_energy_used / profile.max_energy_score) - profile.w_energy
        )

        total: float = w_duration + w_complexity + w_energy

        w_duration = (w_duration / total) * cls.RANKING_SCALE
        w_complexity = (w_complexity / total) * cls.RANKING_SCALE
        w_energy = (w_energy / total) * cls.RANKING_SCALE

        return dict(
            w_duration=max(0.5, min(w_duration, 5.0)),
            w_complexity=max(0.5, min(w_complexity, 5.0)),
            w_energy=max(0.5, min(w_energy, 5.0)),
        )

    # -----------------------------------------------------
    # Fatigue and skip behaviour
    # -----------------------------------------------------

    @staticmethod
    def _learn_fatigue_and_skip(
        profile: UserBehaviorProfile,
        metrics: UserBehaviorMetrics,
        lr: float,
    ) -> dict[str, float]:
        """Adjust fatigue weight and skip penalty based on observed ratios."""

        total_actions: int = metrics.total_tasks_completed + metrics.total_tasks_skipped
        skip_ratio: float = metrics.total_tasks_skipped / max(1, total_actions)
        abandon_ratio: float = metrics.total_tasks_abandoned / max(1, total_actions)
        energy_fatigue: float = profile.energy_fatigue_weight * (1.0 + abandon_ratio)
        skip_penalty: float = profile.skip_penalty + lr * (
            skip_ratio - profile.skip_penalty
        )

        return dict(
            energy_fatigue_weight=energy_fatigue,
            skip_penalty=skip_penalty,
        )

    # -----------------------------------------------------
    # Cognitive limits (focus cycles)
    # -----------------------------------------------------

    @staticmethod
    def _learn_cognitive_limits(
        profile: UserBehaviorProfile,
        metrics: UserBehaviorMetrics,
        lr: float,
    ) -> dict[str, float]:
        """Adjust ultradian limit based on average focus block length."""

        new_ultradian: int = profile.ultradian_limit

        if metrics.avg_focus_block_minutes > 0:
            observed_limit: float = metrics.avg_focus_block_minutes * 1.2
            new_ultradian = int(
                profile.ultradian_limit
                + lr * (observed_limit - profile.ultradian_limit)
            )

        return dict(ultradian_limit=max(25, min(new_ultradian, 120)))

    # -----------------------------------------------------
    # Momentum dynamics
    # -----------------------------------------------------

    @staticmethod
    def _learn_momentum(
        profile: UserBehaviorProfile,
        metrics: UserBehaviorMetrics,
        lr: float,
    ) -> dict[str, float]:
        """Adjust momentum decay gap based on completion intervals."""

        new_gap: int = profile.momentum_decay_gap_minutes

        if metrics.avg_completion_interval_minutes > 0:
            target_gap: float = metrics.avg_completion_interval_minutes * 1.5
            new_gap = int(
                profile.momentum_decay_gap_minutes
                + lr * (target_gap - profile.momentum_decay_gap_minutes)
            )

        return dict(momentum_decay_gap_minutes=max(10, min(new_gap, 60)))

    # -----------------------------------------------------
    # Exploration
    # -----------------------------------------------------

    @staticmethod
    def _learn_exploration(
        profile: UserBehaviorProfile,
        metrics: UserBehaviorMetrics,
    ) -> dict[str, float]:
        """Reduce exploration noise as experience grows."""

        experience: int = metrics.total_tasks_completed
        exploration: float = profile.exploration_noise / (experience**0.5 + 1)

        return dict(exploration_noise=max(0.05, exploration))

    # -----------------------------------------------------
    # Preferences
    # -----------------------------------------------------

    @staticmethod
    def _learn_preferences(
        profile: UserBehaviorProfile,
        metrics: UserBehaviorMetrics,
        lr: float,
    ) -> dict[str, float]:
        """Adjust preferred task duration, complexity, and energy usage."""

        pref_duration: float = profile.preferred_task_duration + lr * (
            metrics.avg_task_duration_minutes - profile.preferred_task_duration
        )
        pref_complexity: float = profile.preferred_task_complexity + lr * (
            metrics.avg_task_complexity - profile.preferred_task_complexity
        )
        pref_energy: float = profile.preferred_energy_usage + lr * (
            metrics.avg_energy_used - profile.preferred_energy_usage
        )

        return dict(
            preferred_task_duration=pref_duration,
            preferred_task_complexity=pref_complexity,
            preferred_energy_usage=pref_energy,
        )

    # -----------------------------------------------------
    # Sustainable capacity
    # -----------------------------------------------------

    @staticmethod
    def _learn_capacity(
        profile: UserBehaviorProfile,
        metrics: UserBehaviorMetrics,
    ) -> dict[str, float]:
        """Adjust sustainable capacity limits for duration and complexity."""

        duration_cap: float = max(
            profile.max_sustainable_duration, metrics.avg_task_duration_minutes * 1.5
        )
        complexity_cap: float = max(
            profile.max_sustainable_complexity, metrics.avg_task_complexity * 1.5
        )

        return dict(
            max_sustainable_duration=duration_cap,
            max_sustainable_complexity=complexity_cap,
        )

    # -----------------------------------------------------
    # Pause behaviour
    # -----------------------------------------------------

    @staticmethod
    def _learn_pause_patterns(
        profile: UserBehaviorProfile,
        metrics: UserBehaviorMetrics,
        lr: float,
    ) -> dict[str, float]:
        """Adjust average pause minutes based on observed rest patterns."""

        if metrics.avg_pause_minutes == 0:
            return {}

        avg_pause: float = profile.avg_pause_minutes + lr * (
            metrics.avg_pause_minutes - profile.avg_pause_minutes
        )

        return dict(avg_pause_minutes=avg_pause)
