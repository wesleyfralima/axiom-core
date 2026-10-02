"""What happened to a task, one entry per change (``axpro task log``)."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

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
    RESTORED = "restored"
    UNDONE = "undone"
    STARTED = "started"
    PAUSED = "paused"


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
        entry_id (UUID): The entry's identity (its event's id).
        previous (dict | None): The task before the change, for undo.
        caused_by (UUID | None): The entry whose change made this one on its
            own.
        undoes (UUID | None): For an "undone" entry, the entry it undid.
        device_id (UUID | None): The device that made the change (set by the
            storage once the device syncs).
        command_id (UUID | None): The command the user typed that made it
            (every change of ``task done a b c`` shares one): undo takes the
            whole command back. None before commands were recorded.
    """

    task_id: TaskId
    user_id: UserId
    occurred_at: datetime
    action: TaskAction
    changes: tuple[FieldChange, ...] = field(default_factory=tuple)
    note: str | None = None
    # The event it came from (its id): what `undoes` and `caused_by` point to
    entry_id: UUID = field(default_factory=uuid4)
    # The task before the change (``Task.snapshot``), to undo it
    previous: dict[str, Any] | None = None
    # Made on its own by another entry's change (the next occurrence of a
    # completed task): undone with that one, never alone
    caused_by: UUID | None = None
    # For an "undone" entry, the entry it undid
    undoes: UUID | None = None
    # The device that made the change, once the user syncs (None: this
    # device, before it joined)
    device_id: UUID | None = None
    # The command typed (one per `axpro …` run): one undo takes it all back
    command_id: UUID | None = None
