from dataclasses import dataclass
from datetime import datetime

from a_core import DomainEvent
from b_domain.value_objects import ContextId, TaskId, UserId
from b_domain.value_objects.enums import EnergyLevel, TaskComplexity


@dataclass(frozen=True, kw_only=True)
class TaskCreatedEvent(DomainEvent):
    """Triggered when a new task is created."""

    title: str
    task_id: TaskId
    due_date: datetime | None = None
    user_id: UserId | None = None


@dataclass(frozen=True, kw_only=True)
class TaskEditedEvent(DomainEvent):
    """Triggered when an existing task is edited.

    Attributes:
        task_id (TaskId): Identifier of the task.
        user_id (UserId): Identifier of the user.
        changes (dict[str, list[str | None]]): Field → ``[before, after]``, as
            text (dates in ISO 8601, None for "none").
    """

    task_id: TaskId
    user_id: UserId
    changes: dict[str, list[str | None]]


@dataclass(frozen=True, kw_only=True)
class TaskReopenedEvent(DomainEvent):
    """Triggered when a done or cancelled task is reopened."""

    task_id: TaskId
    user_id: UserId


@dataclass(frozen=True, kw_only=True)
class TaskArchivedEvent(DomainEvent):
    """Triggered when a closed task is archived."""

    task_id: TaskId
    user_id: UserId


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
        task_complexity (TaskComplexity): Complexity level of the task.
    """

    task_id: TaskId
    user_id: UserId
    estimated_minutes: int
    actual_minutes: int
    energy_level_used: EnergyLevel
    task_complexity: TaskComplexity


@dataclass(frozen=True, kw_only=True)
class TaskCancelledEvent(DomainEvent):
    """Triggered when the user cancels a task.

    Attributes:
        task_id (TaskId): Identifier of the task.
        user_id (UserId): Identifier of the user.
        end_series (bool): For a recurring task, whether the whole series ends
            here; otherwise only this occurrence is skipped and the series
            goes on.
    """

    task_id: TaskId
    user_id: UserId
    end_series: bool = False


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
    """Triggered when a task is deleted (its history stays).

    Attributes:
        task_id (TaskId): Identifier of the task.
        user_id (UserId): Identifier of the user.
        title (str): The title it had, for the history.
    """

    task_id: TaskId
    user_id: UserId
    title: str
