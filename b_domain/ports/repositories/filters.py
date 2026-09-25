from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from a_core import UniqueId
from b_domain.value_objects import ContextId, Priority, TaskId, TaskStatus, UserId
from b_domain.value_objects.enums import EnergyLevel, TaskComplexity


@dataclass(kw_only=True)
class BaseFilter:
    """Base class for all repository filters providing standard pagination.

    Attributes:
        limit (int): Maximum number of records to return.
            Defaults to 100 to prevent OOM.
        offset (int): Number of records to skip. Defaults to 0.
        ids (Optional[list[UniqueId]]): Batch fetching by IDs (e.g., WHERE id IN (...)).
        created_after (Optional[datetime]): Filter records created after this timestamp.
        created_before (Optional[datetime]): Filter records created
            before this timestamp.
        updated_after (Optional[datetime]): Filter records updated after this timestamp.
        updated_before (Optional[datetime]): Filter records updated
            before this timestamp.
    """

    limit: int = 100
    offset: int = 0

    # Batch fetching
    ids: list[UniqueId] | None = None

    # Time ranges (created_at)
    created_after: datetime | None = None
    created_before: datetime | None = None

    # Time ranges (updated_at)
    updated_after: datetime | None = None
    updated_before: datetime | None = None


@dataclass(kw_only=True)
class TaskFilter(BaseFilter):
    """Encapsulates search criteria for querying Tasks.

    Allows adding new filters in the future without breaking method signatures
    in the TaskRepository.

    Attributes:
        user_id (Optional[UserId]): Filter tasks by user ID.
        parent_id (Optional[TaskId]): Filter tasks by parent task ID.
        status (Optional[TaskStatus]): Filter tasks by status.
        priority (Optional[Priority]): Filter tasks by priority.
        context_id (Optional[ContextId]): Filter tasks by GTD context.
        max_energy_level (Optional[EnergyLevel]): Filter tasks
            requiring up to this energy level.
        complexity (Optional[TaskComplexity]): Filter tasks by complexity.
        due_before (Optional[datetime]): Filter tasks due before this timestamp.
        due_after (Optional[datetime]): Filter tasks due after this timestamp.
        is_blocked (Optional[bool]): Filter blocked tasks.
        is_recurring (Optional[bool]): Filter recurring tasks.
        only_roots (bool): If True, only return root tasks (no parents).
        tags (list[str]): Filter tasks by tags.
    """

    user_id: UserId | None = None
    parent_id: TaskId | None = None
    status: TaskStatus | None = None
    priority: Priority | None = None
    context_id: ContextId | None = None

    # GTD filters
    max_energy_level: EnergyLevel | None = None
    complexity: TaskComplexity | None = None

    # Scheduling filters
    due_before: datetime | None = None
    due_after: datetime | None = None

    # Behavior filters
    is_blocked: bool | None = None
    is_recurring: bool | None = None

    only_roots: bool = False
    tags: list[str] = field(default_factory=list)


@dataclass(kw_only=True)
class UserFilter(BaseFilter):
    """Encapsulates search criteria for querying Users.

    Useful for admin panels or searching users to share projects with.

    Attributes:
        username (Optional[str]): Filter users by username.
        email (Optional[str]): Filter users by email.
        is_active (Optional[bool]): Filter users by active status.
    """

    username: str | None = None
    email: str | None = None
    is_active: bool | None = None


@dataclass(kw_only=True)
class ContextFilter(BaseFilter):
    """Encapsulates search criteria for querying GTD Contexts.

    Attributes:
        user_id (Optional[UserId]): Filter contexts by user ID.
        name_contains (Optional[str]): Filter contexts by name
            substring (useful for type-ahead search).
    """

    user_id: UserId | None = None
    name_contains: str | None = None


@dataclass(kw_only=True)
class TimeEntryFilter(BaseFilter):
    """Encapsulates search criteria for Time Tracking (Pomodoros/Logs).

    Crucial for generating reports (e.g., "How many hours did I work this week?").

    Attributes:
        user_id (Optional[UserId]): Filter time entries by user ID.
        task_id (Optional[TaskId]): Filter time entries by task ID.
        started_after (Optional[datetime]): Filter entries started after this timestamp.
        started_before (Optional[datetime]): Filter entries
            started before this timestamp.
        is_running (Optional[bool]): If True, filter entries where end_time is NULL.
    """

    user_id: UserId | None = None
    task_id: Optional["TaskId"] = None

    # Report ranges
    started_after: datetime | None = None
    started_before: datetime | None = None

    # State
    is_running: bool | None = None


@dataclass(kw_only=True)
class OutboxEventFilter(BaseFilter):
    """Encapsulates search criteria for the Outbox Relay Worker.

    This is strictly an infrastructure filter, rarely used by end-users.

    Attributes:
        is_processed (Optional[bool]): Filter events by processed state.
        scheduled_before (Optional[datetime]): Filter events
            scheduled before this timestamp.
        aggregate_type (Optional[str]): Filter events by aggregate type.
        has_errors (Optional[bool]): Filter events with errors (retry_count > 0).
    """

    is_processed: bool | None = None
    scheduled_before: datetime | None = None
    aggregate_type: str | None = None
    has_errors: bool | None = None
