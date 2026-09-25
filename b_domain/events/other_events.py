from dataclasses import dataclass

from a_core import DomainEvent
from b_domain.value_objects.identifiers import ContextId, UserId


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
        reward_type (str): Type of reward (e.g.,
            "streak_milestone", "performance_bonus").
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
    old_context_id: ContextId | None
    new_context_id: ContextId
    trigger_type: str = "manual"
