"""What happened to a task, one entry per change (``axpro task log``)."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from b_domain.value_objects.identifiers import TaskId, UserId


class TaskAction(StrEnum):
    """The kinds of change the history records."""

    CREATED = "created"
    EDITED = "edited"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REOPENED = "reopened"
    ARCHIVED = "archived"
    DELETED = "deleted"


@dataclass(frozen=True, kw_only=True)
class FieldChange:
    """One field of an edit: its name and the values before and after, as text
    (a date as ISO 8601; None for "none")."""

    field: str
    before: str | None
    after: str | None


@dataclass(frozen=True, kw_only=True)
class TaskHistoryEntry:
    """One change to a task.

    Kept apart from the task (no foreign key to it): the history of a deleted
    task stays, for undo and restore.

    Attributes:
        task_id (TaskId): The task.
        user_id (UserId): Its owner (history is read per user).
        occurred_at (datetime): When it happened.
        action (TaskAction): What happened.
        changes (tuple[FieldChange, ...]): For an edit, what changed.
        note (str | None): Anything else worth keeping ("the series ends
            here", "approximate: before the history existed").
    """

    task_id: TaskId
    user_id: UserId
    occurred_at: datetime
    action: TaskAction
    changes: tuple[FieldChange, ...] = field(default_factory=tuple)
    note: str | None = None
