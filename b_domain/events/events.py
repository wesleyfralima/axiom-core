from dataclasses import dataclass
from typing import Optional

from a_core.base import DomainEvent
from b_domain.value_objects.enums import EnergyLevel
from b_domain.value_objects.identifiers import ContextId, TaskId, UserId


@dataclass(frozen=True, kw_only=True)
class TaskStartedEvent(DomainEvent):
    """Triggered when a user starts working on a task.

    Attributes:
        task_id (TaskId): Identifier of the task.
        user_id (UserId): Identifier of the user.
        context_id (ContextId): Context in which the task was started.
        momentum_at_start (float): Momentum value at the start of the task.
    """
    task_id: TaskId
    user_id: UserId
    context_id: ContextId
    momentum_at_start: float


@dataclass(frozen=True, kw_only=True)
class TaskCompletedEvent(DomainEvent):
    """Triggered when a task is successfully completed by the user.

    Attributes:
        task_id (TaskId): Identifier of the task.
        user_id (UserId): Identifier of the user.
        estimated_minutes (int): Estimated duration of the task.
        actual_minutes (int): Actual duration spent on the task.
        energy_level_used (EnergyLevel): Energy level applied during execution.
    """
    task_id: TaskId
    user_id: UserId
    estimated_minutes: int
    actual_minutes: int
    energy_level_used: EnergyLevel


@dataclass(frozen=True, kw_only=True)
class TaskAbandonedEvent(DomainEvent):
    """Triggered when the user abandons a task in progress.

    Attributes:
        task_id (TaskId): Identifier of the task.
        user_id (UserId): Identifier of the user.
        time_spent_minutes (int): Time spent before abandoning.
        reason (str): Reason inferred for abandonment (e.g., "timeout", "manual_skip").
    """
    task_id: TaskId
    user_id: UserId
    time_spent_minutes: int
    reason: str = "manual_skip"


@dataclass(frozen=True, kw_only=True)
class FlowMomentumBrokenEvent(DomainEvent):
    """Triggered when the system detects that the user's streak has been reset.

    Attributes:
        user_id (UserId): Identifier of the user.
        last_streak_count (int): Number of consecutive tasks completed before the break.
    """
    user_id: UserId
    last_streak_count: int


@dataclass(frozen=True, kw_only=True)
class RewardEarnedEvent(DomainEvent):
    """Triggered when the user earns a reward.

    Attributes:
        user_id (UserId): Identifier of the user.
        reward_type (str): Type of reward (e.g., "streak_milestone", "performance_bonus").
        value (int): Value or points associated with the reward.
    """
    user_id: UserId
    reward_type: str
    value: int


@dataclass(frozen=True, kw_only=True)
class ContextSwitchedEvent(DomainEvent):
    """Triggered when the user's active context changes.

    This event is essential for the Context Engine to learn transition patterns.

    Attributes:
        user_id (UserId): Identifier of the user.
        old_context_id (Optional[ContextId]): Previous context, if any.
        new_context_id (ContextId): New active context.
        trigger_type (str): How the switch was triggered ("manual" or "automatic",
            e.g., by geofencing or schedule). Defaults to "manual".
    """
    user_id: UserId
    old_context_id: Optional[ContextId]
    new_context_id: ContextId
    trigger_type: str = "manual"
