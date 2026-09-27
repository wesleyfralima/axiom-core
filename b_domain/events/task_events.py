from dataclasses import dataclass
from datetime import datetime
from typing import Any

from a_core import DomainEvent, UniqueId
from b_domain.value_objects import ContextId, TaskId, UserId
from b_domain.value_objects.enums import EnergyLevel, TaskComplexity


@dataclass(frozen=True, kw_only=True)
class TaskCreatedEvent(DomainEvent):
    """Triggered when a new task is created."""

    title: str
    task_id: TaskId
    due_date: datetime | None = None
    user_id: UserId | None = None
    # The event of the user's action that made the task on its own (the next
    # occurrence of a completed one); None when the user created it
    caused_by: UniqueId | None = None


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
    # The task before this change (``Task.snapshot``), for undo
    previous: dict[str, Any] | None = None


@dataclass(frozen=True, kw_only=True)
class TaskReopenedEvent(DomainEvent):
    """Triggered when a done or cancelled task is reopened."""

    task_id: TaskId
    user_id: UserId
    # The task before this change (``Task.snapshot``), for undo
    previous: dict[str, Any] | None = None


@dataclass(frozen=True, kw_only=True)
class TaskArchivedEvent(DomainEvent):
    """Triggered when a closed task is archived."""

    task_id: TaskId
    user_id: UserId
    # The task before this change (``Task.snapshot``), for undo
    previous: dict[str, Any] | None = None


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
    context_id: ContextId | None = None
    momentum_at_start: float = 0.0
    # The task before this change (``Task.snapshot``), for undo
    previous: dict[str, Any] | None = None


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
    # The task before this change (``Task.snapshot``), for undo
    previous: dict[str, Any] | None = None
    # The change that made this one on its own (a parent's completion)
    caused_by: UniqueId | None = None


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
    # The task before this change (``Task.snapshot``), for undo
    previous: dict[str, Any] | None = None


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
    # The task before this change (``Task.snapshot``), for undo
    previous: dict[str, Any] | None = None
    # The change that made this one on its own (a parent's delete)
    caused_by: UniqueId | None = None


@dataclass(frozen=True, kw_only=True)
class TaskRestoredEvent(DomainEvent):
    """Triggered when a deleted task is brought back."""

    task_id: TaskId
    user_id: UserId
    # The change that made this one on its own (a parent's restore)
    caused_by: UniqueId | None = None


@dataclass(frozen=True, kw_only=True)
class TaskUndoneEvent(DomainEvent):
    """Triggered when a change to the task is undone.

    Attributes:
        task_id (TaskId): Identifier of the task.
        user_id (UserId): Identifier of the user.
        undoes (UniqueId): The history entry (its event's id) undone.
        action (str): What was undone ("completed", "edited"…).
    """

    task_id: TaskId
    user_id: UserId
    undoes: UniqueId
    action: str


@dataclass(frozen=True, kw_only=True)
class TaskPausedEvent(DomainEvent):
    """Triggered when the user pauses a task in progress (its timer stops).

    Attributes:
        task_id (TaskId): Identifier of the task.
        user_id (UserId): Identifier of the user.
        minutes (int): How long the session that just ended lasted.
    """

    task_id: TaskId
    user_id: UserId
    minutes: int = 0
    # The task before this change (``Task.snapshot``), for undo
    previous: dict[str, Any] | None = None
    # The start of another task that paused this one on its own
    caused_by: UniqueId | None = None
