from dataclasses import dataclass, field
from datetime import datetime

from a_core import DTO
from b_domain.value_objects.enums import EnergyLevel
from c_application.dtos.context_dtos import ContextOutputDTO
from c_application.dtos.recurrence_dtos import RecurrenceInputDTO, RecurrenceOutputDTO
from c_application.utils.date_input import DateInput


@dataclass(frozen=True, kw_only=True)
class CreateTaskInputDTO(DTO):
    """Data Transfer Object for creating a new Task.

    This DTO is used when a new task is being created. It contains
    all the necessary information to initialize a task entity.
    """

    # Core identifiers
    user_id: str
    title: str
    description: str = ""

    # Priority and energy requirements (no priority: the user's default)
    priority: int | None = None
    required_energy_level: int = EnergyLevel.BALANCED.value

    # GTD context: its name or ID prefix (none: the user's active context)
    context_id: str | None = None

    # Due date: a datetime, a date (gets the user's default due time) or an
    # expression such as "tomorrow 14:00" (see c_application/utils/date_input)
    due_date: DateInput | None = None
    is_floating: bool = True
    timezone: str | None = None

    # Hierarchy and dependencies
    parent_id: str | None = None
    depends_on: set[str] = field(default_factory=set)

    # Recurrence configuration
    recurrence: RecurrenceInputDTO | None = None


@dataclass(frozen=True, kw_only=True)
class UpdateTaskInputDTO(DTO):
    """Data Transfer Object for updating an existing Task.

    This DTO is used when updating an existing task. It allows
    partial updates, meaning only the provided fields will be changed.
    """

    # Core identifiers
    task_id_prefix: str
    user_id: str

    # Editable fields (optional for partial updates)
    title: str | None = None
    description: str | None = None
    priority: str | None = None

    # Context: its name or ID prefix; remove_context takes it out of any
    context_id: str | None = None
    remove_context: bool = False
    # Energy: a level name or number ("high", 4)
    energy_level: str | int | None = None

    # Due date: as in CreateTaskInputDTO; remove_due_date clears it
    due_date: DateInput | None = None
    remove_due_date: bool = False
    is_floating: bool | None = None
    timezone: str | None = None

    # Recurrence: a new rule (its start_date defaults to the task's due date,
    # which stays — the occurrences after it follow the new rule), or
    # remove_recurrence to stop repeating
    recurrence: RecurrenceInputDTO | None = None
    remove_recurrence: bool = False


@dataclass(frozen=True, kw_only=True)
class TaskOutputDTO(DTO):
    """Data Transfer Object for returning Task information.

    This DTO is used when returning task details to the client
    or presenter layer. It contains all relevant information
    about a task, including metadata, deadlines, and recurrence display.
    """

    # Core identifiers and metadata
    id: str
    title: str
    description: str | None = None
    status: str
    priority: str

    # Contextual information (the task's GTD context)
    context_id: str | None = None
    context_name: str | None = None
    context_icon: str | None = None
    required_energy_level: int | None = None
    is_blocked: bool = False

    # Audit timestamps
    created_at: datetime
    updated_at: datetime

    # Hierarchy and deadlines
    parent_id: str | None = None
    due_date: datetime | None = None
    is_overdue: bool = False

    # Recurrence and scheduling
    recurrence_display: str | None = None
    # The rule as editable fields (None: does not repeat)
    recurrence: RecurrenceOutputDTO | None = None
    next_occurrences: list[datetime] = field(default_factory=list)

    # Focus state (e.g., currently active or highlighted)
    is_in_focus: bool = False

    # A future occurrence of a recurring task, projected: it does not exist
    # yet (``id`` is the current occurrence's)
    is_projected: bool = False


@dataclass(frozen=True, kw_only=True)
class CreateTaskOutputDTO(TaskOutputDTO):
    """Output DTO for task creation.

    Represents the result of creating a new task.
    Inherits all fields from TaskOutputDTO.
    """


@dataclass(frozen=True)
class TaskByUserRequest(DTO):
    """Request DTO for fetching a task by user.

    This DTO is used when requesting a specific task associated
    with a given user. It provides the identifiers needed for lookup
    and optionally includes completion metadata.
    """

    # Identifiers
    task_id_prefix: str
    user_id: str

    # Completion metadata
    completed_at: datetime | None = None


@dataclass(frozen=True, kw_only=True)
class CancelTaskInputDTO(DTO):
    """Request DTO for cancelling one of the user's tasks.

    Attributes:
        task_id_prefix (str): The task's ID or ID prefix.
        user_id (str): The user who owns the task.
        end_series (bool): For a recurring task, end the whole series instead
            of skipping only this occurrence.
    """

    task_id_prefix: str
    user_id: str
    end_series: bool = False


@dataclass(frozen=True, kw_only=True)
class TaskStatusChangedOutputDTO(DTO):
    """The result of reopening, archiving or cancelling a task.

    Attributes:
        task (TaskOutputDTO): The task, already in its new status.
        series_ended (bool): A recurring task was cancelled with
            ``end_series``: no next occurrence comes.
    """

    task: TaskOutputDTO
    series_ended: bool = False


@dataclass(frozen=True, kw_only=True)
class CompleteTaskOutputDTO(DTO):
    """Composite DTO for the result of completing a task.

    This DTO encapsulates both the completed task and, if applicable,
    the next occurrence generated by recurrence rules.
    """

    # The task that has just been completed
    completed_task: TaskOutputDTO

    # The next occurrence of the task, if recurrence rules apply
    next_occurrence: TaskOutputDTO | None = None


@dataclass(frozen=True, kw_only=True)
class GetTaskRequest(DTO):
    """Request DTO for retrieving a specific task.

    This DTO is used when fetching details of a task associated
    with a given user. It supports retrieving multiple upcoming
    occurrences if the task is recurrent.
    """

    # Identifiers
    task_id_prefix: str
    user_id: str

    # How far to project a recurring task's next occurrences: a number of
    # days or a date (None: the user's days_ahead preference)
    ahead: int | DateInput | None = None


@dataclass(frozen=True, kw_only=True)
class ListTasksRequest(DTO):
    """Request DTO for listing tasks with comprehensive filtering and pagination.

    This DTO mirrors the TaskFilter but uses primitive types to decouple
    the Application layer from Domain Value Objects. It allows flexible
    filtering, sorting, and pagination when retrieving tasks.
    """

    # Identifiers
    ids: list[str] | None = None
    user_id: str
    parent_id: str | None = None

    # Status & Priority
    status: str | None = None
    # False hides done/cancelled; archived ones only show when asked by status
    include_closed: bool = True
    priority: str | None = None

    # GTD & Organization (context: its name or ID prefix)
    context_id: str | None = None
    # Without context_id, limit the list to the user's active context (if any)
    use_active_context: bool = False
    max_energy: int | None = None
    complexity: str | None = None
    tags: list[str] = field(default_factory=list)

    # Behavior Flags
    include_blocked: bool = True  # Maps to is_blocked in TaskFilter
    is_recurring: bool | None = None
    only_roots: bool = False

    # Temporal Filters (Task Specific); a date alone means its midnight
    due_before: DateInput | None = None
    due_after: DateInput | None = None

    # Project recurring tasks' future occurrences up to a number of days or a
    # date (None: the user's days_ahead preference; 0: only today)
    ahead: int | DateInput | None = None

    # Pagination (from BaseFilter)
    limit: int = 100
    offset: int = 0

    # Auditing Filters (from BaseFilter)
    created_after: datetime | None = None
    created_before: datetime | None = None
    updated_after: datetime | None = None
    updated_before: datetime | None = None


@dataclass(frozen=True)
class TaskListOutputDTO(DTO):
    """Output DTO representing a list of tasks.

    This DTO is used when returning a collection of tasks to the client
    or presenter layer. It encapsulates multiple task details in a single
    response, typically after applying filters or pagination.
    """

    # Collection of task output DTOs
    tasks: list[TaskOutputDTO]

    # The context the list is limited to (requested, or the active one);
    # None when the list spans every context
    context: ContextOutputDTO | None = None

    # Future occurrences of the listed recurring tasks, not created yet
    # (``is_projected``), up to the horizon; sorted by due date
    projected: list[TaskOutputDTO] = field(default_factory=list)
