from dataclasses import dataclass

from a_core import ValueObject
from b_domain.value_objects import UserId


@dataclass(frozen=True, kw_only=True)
class UserBehaviorProfile(ValueObject):
    """Represents the learned behavioral parameters of a user.

    Unlike `UserFlowState` (which captures momentary state),
    this object describes how the user tends to behave over time.
    It aggregates long-term preferences, cognitive limits, fatigue,
    recovery patterns, and motivational dynamics.

    Attributes:
        user_id (UserId): Identifier of the user.
        w_complexity (float): Weight for task complexity in ranking.
        w_duration (float): Weight for task duration in ranking.
        w_energy (float): Weight for energy usage in ranking.
        w_priority (float): Weight for task priority in ranking.
        max_complexity_score (float): Maximum normalized complexity score.
        max_duration_score (float): Maximum normalized duration score.
        max_energy_score (float): Maximum normalized energy score.
        ultradian_limit (int): Cognitive limit for focus cycles in minutes.
        warmup_duration_limit (int): Warm-up duration limit in minutes.
        momentum_base_reward (float): Base reward for momentum.
        momentum_decay_gap_minutes (int): Gap in minutes before momentum decays.
        momentum_decay_penalty (float): Penalty applied when momentum decays.
        skip_penalty (float): Penalty applied when tasks are skipped.
        diversity_penalty (float): Penalty applied to encourage task diversity.
        momentum_energy_weight (float): Contribution of energy to momentum gain.
        momentum_complexity_weight (float): Contribution of complexity to momentum gain.
        energy_fatigue_weight (float): Impact of tasks on energy fatigue.
        complexity_fatigue_weight (float): Impact of tasks on complexity fatigue.
        rest_recovery_minutes_per_level (int): Recovery minutes per rest level.
        power_nap_min_minutes (int): Minimum duration for a power nap.
        avg_pause_minutes (float): Average duration of pauses in minutes.
        exploration_noise (float): Exploration noise factor to prevent stagnation.
        preferred_task_duration (float): User’s preferred task duration in minutes.
        preferred_task_complexity (float): User’s preferred task complexity level.
        preferred_energy_usage (float): User’s preferred energy usage level.
        max_sustainable_duration (float): Maximum sustainable task duration.
        max_sustainable_complexity (float): Maximum sustainable task complexity.
    """

    user_id: UserId

    # ---------------------------------------------------------
    # FLOW ENGINE WEIGHTS
    # (Relative importance in ranking)
    # ---------------------------------------------------------
    w_complexity: float = 2.0
    w_duration: float = 1.5
    w_energy: float = 2.5
    w_priority: float = 2.0

    # ---------------------------------------------------------
    # NORMALIZED SCORE SCALES
    # (Used to transform absolute values into scores)
    # ---------------------------------------------------------
    max_complexity_score: float = 10.0
    max_duration_score: float = 5.0
    max_energy_score: float = 10.0

    # ---------------------------------------------------------
    # HUMAN COGNITIVE LIMITS
    # ---------------------------------------------------------
    ultradian_limit: int = 90
    warmup_duration_limit: int = 10

    # ---------------------------------------------------------
    # MOMENTUM DYNAMICS
    # (Behavioral motivation)
    # ---------------------------------------------------------
    momentum_base_reward: float = 0.10
    momentum_decay_gap_minutes: int = 20
    momentum_decay_penalty: float = 0.15
    skip_penalty: float = 0.10
    diversity_penalty: float = 0.15

    # ---------------------------------------------------------
    # CONTRIBUTIONS TO MOMENTUM GAIN
    # ---------------------------------------------------------
    momentum_energy_weight: float = 0.04
    momentum_complexity_weight: float = 0.03

    # ---------------------------------------------------------
    # COGNITIVE FATIGUE
    # (Impact of tasks on energy)
    # ---------------------------------------------------------
    energy_fatigue_weight: float = 1.0
    complexity_fatigue_weight: float = 1.0

    # ---------------------------------------------------------
    # ENERGY RECOVERY / PAUSE BEHAVIOR
    # ---------------------------------------------------------
    rest_recovery_minutes_per_level: int = 15
    power_nap_min_minutes: int = 10
    avg_pause_minutes: float = 0.0

    # ---------------------------------------------------------
    # ENGINE EXPLORATION
    # (Anti-stagnation)
    # ---------------------------------------------------------
    exploration_noise: float = 0.5

    # -----------------------------------
    # USER PREFERENCES
    # -----------------------------------
    preferred_task_duration: float = 20.0
    preferred_task_complexity: float = 4.0
    preferred_energy_usage: float = 4.0

    # -----------------------------------
    # OBSERVED CAPACITY
    # -----------------------------------
    max_sustainable_duration: float = 60.0
    max_sustainable_complexity: float = 8.0
