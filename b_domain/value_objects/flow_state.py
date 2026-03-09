from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Optional

from a_core.base import ValueObject
from b_domain.value_objects import UserId, ContextId
from b_domain.value_objects.enums import EnergyLevel, MomentumTrend, TaskComplexity
from b_domain.value_objects.user_behavior_profile import UserBehaviorProfile


@dataclass(frozen=True, kw_only=True)
class UserFlowState(ValueObject):
    """Represents the system’s awareness of the user’s condition.

    Combines behavioral momentum logic with real-time precision.
    Tracks session anchors, energy levels, momentum dynamics,
    skips, and task complexity to guide flow decisions.
    """

    user_id: UserId
    active_context_id: Optional[ContextId] = None

    # --- Real-time anchors ---
    session_ends_at: datetime  # When the user plans to stop
    focus_started_at: datetime  # When the current focus block started

    # --- Biopsychological dimensions ---
    current_energy: EnergyLevel

    # --- Momentum dynamics ---
    momentum_streak: int = 0
    momentum_score: float = 0.0  # Range: 0.0 to 1.0
    last_completion_at: Optional[datetime] = None

    # --- Session settings ---
    session_target_minutes: Optional[int] = None
    consecutive_skips: int = 0

    last_task_complexity: Optional[TaskComplexity] = None

    # ------------------------------------------------------------------
    # Real-time properties
    # ------------------------------------------------------------------

    def get_available_minutes(self, now: datetime) -> int:
        """Calculate how much real time remains until the end of the session."""
        if now >= self.session_ends_at:
            return 0
        delta: timedelta = self.session_ends_at - now
        return int(delta.total_seconds() // 60)

    def get_continuous_focus_minutes(self, now: datetime) -> int:
        """Calculate uninterrupted focus time (used to trigger breaks)."""
        if self.focus_started_at is None:
            return 0
        delta: timedelta = now - self.focus_started_at
        return int(delta.total_seconds() // 60)

    @property
    def momentum_trend(self) -> MomentumTrend:
        """Identify the `MomentumTrend` based on the current `momentum_score`.

        - ≥ 0.8 → Rising momentum
        - ≥ 0.4 → Stable flow
        - > 0   → Falling momentum
        - = 0   → Stagnant
        """
        if self.momentum_score >= 0.8:
            return MomentumTrend.RISING
        if self.momentum_score >= 0.4:
            return MomentumTrend.STABLE
        if self.momentum_score > 0:
            return MomentumTrend.FALLING
        return MomentumTrend.STAGNANT

    # ------------------------------------------------------------------
    # STATE TRANSITIONS (Immutability)
    # ------------------------------------------------------------------

    def record_completion(
            self,
            now: datetime,
            energy: EnergyLevel,
            complexity: TaskComplexity,
            profile: UserBehaviorProfile,
    ) -> "UserFlowState":
        """Record a task completion.

        Increases momentum (dopamine effect) and drains energy (fuel).
        Momentum gain is weighted by task difficulty, while penalties
        apply if completion intervals exceed decay thresholds.
        """

        # 1. MOMENTUM CALCULATION (Dopamine/Speed)
        interval_penalty = 0.0
        if self.last_completion_at:
            gap = (now - self.last_completion_at).total_seconds() / 60
            if gap > profile.momentum_decay_gap_minutes:
                interval_penalty = profile.momentum_decay_penalty

        # Weighted reward: harder tasks generate more momentum
        base_reward = profile.momentum_base_reward
        energy_bonus = energy.value * profile.momentum_energy_weight
        complexity_bonus = complexity.value * profile.momentum_complexity_weight

        increment = base_reward + energy_bonus + complexity_bonus - interval_penalty
        new_momentum_score = max(0.0, min(1.0, self.momentum_score + increment))

        # 2. ENERGY DECREASE CALCULATION (Battery)
        # Rule: If the task required real effort (Energy ≥ Balanced)
        # or mental effort (Complexity ≥ Medium), the user gets tired.
        new_energy_val = self.current_energy.value

        # Total effort load
        effort_load = (
                energy.value * profile.energy_fatigue_weight +
                complexity.value * profile.complexity_fatigue_weight
        )

        # If effort is significant (e.g., ≥ 4), reduce one energy level
        # HIGH (3) -> BALANCED (2) -> LOW (1)
        if effort_load >= 4:
            new_energy_val = max(EnergyLevel.LOW.value, new_energy_val - 1)

        return replace(
            self,
            momentum_streak=self.momentum_streak + 1,
            momentum_score=new_momentum_score,
            current_energy=EnergyLevel(new_energy_val),  # Update energy here!
            last_completion_at=now,
            last_task_complexity=complexity,
            consecutive_skips=0,
        )

    def record_skip(self, profile: UserBehaviorProfile) -> "UserFlowState":
        """Apply penalty for skipping a suggestion (Hook Model)."""
        return replace(
            self,
            momentum_score=max(0.0, self.momentum_score - profile.skip_penalty),
            consecutive_skips=self.consecutive_skips + 1,
        )

    def reset_skips(self) -> "UserFlowState":
        """Reset the number of consecutive skips to zero."""
        return replace(self, consecutive_skips=0)

    def record_abandon(self) -> "UserFlowState":
        """Record a complete flow break (task abandonment)."""
        return replace(
            self,
            momentum_streak=0,
            momentum_score=0.0,
            consecutive_skips=self.consecutive_skips + 1
        )

    def reset_momentum(self) -> "UserFlowState":
        """Reset streak and score but keep session time anchors."""
        return replace(self, momentum_streak=0, momentum_score=0.0)

    def update_context(self, now: datetime, context_id: ContextId) -> "UserFlowState":
        """Change context and restart focus timer (cognitive refresh)."""
        return replace(
            self,
            active_context_id=context_id,
            focus_started_at=now
        )

    def renew_focus(self, now: datetime) -> "UserFlowState":
        """Reset focus timer (time). Useful for cognitive interventions."""
        return replace(self, focus_started_at=now)

    def record_rest(
            self,
            minutes_rested: int,
            profile: UserBehaviorProfile
    ) -> "UserFlowState":
        """Record a rest period and recover energy proportionally.

        - Recovery is proportional to rest duration.
        - Power Nap bonus: resting between 10–14 minutes guarantees at least
          one energy level recovery.
        - Assumption: user cannot reach peak energy after rest, maximum is HIGH.
        """

        # Proportional calculation (minimum of 0 gain)
        energy_gain: int = minutes_rested // profile.rest_recovery_minutes_per_level

        # Power Nap bonus: if rested between more than
        # power_nap_min_minutes minutes but less than
        # rest_recovery_minutes_per_level, guarantee
        # at least 1 level of recovery
        if energy_gain == 0 and minutes_rested >= profile.power_nap_min_minutes:
            energy_gain = 1

        # Theoretically, ser cannot reach EnergyLevel.PEAK
        # only by resting; maximum achievable is EnergyLevel.HIGH
        new_energy_val: int = min(
            EnergyLevel.HIGH.value,
            self.current_energy.value + energy_gain,
        )

        return replace(
            self,
            current_energy=EnergyLevel(new_energy_val),
        )
