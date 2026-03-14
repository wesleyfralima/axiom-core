from dataclasses import dataclass

from a_core.base import DomainEvent
from b_domain.value_objects import TaskId, UserId, ContextId
from b_domain.value_objects.enums import EnergyLevel


@dataclass(frozen=True, kw_only=True)
class TaskCreatedEvent(DomainEvent):
    pass


@dataclass(frozen=True, kw_only=True)
class TaskEditedEvent(DomainEvent):
    pass


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
class TaskDeletedEvent(DomainEvent):
    pass
