from datetime import datetime

from a_core.exceptions import ValidationException
from b_domain.entities import Task
from b_domain.ports.repositories.filters import TaskFilter
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import (
    ContextId,
    Priority,
    TaskId,
    TaskStatus,
    UserId,
)
from b_domain.value_objects.enums import EnergyLevel, TaskComplexity
from c_application.dtos.task_dtos import ListTasksRequest, TaskListOutputDTO
from c_application.mappers.task_mapper import TaskMapper


class ListTasksUseCase(UseCase[ListTasksRequest, TaskListOutputDTO]):
    """Use case for listing tasks with filtering and domain mapping.

    This use case applies comprehensive filters including GTD attributes,
    temporal ranges, and pagination, then maps the results into output DTOs.
    """

    async def execute(self, request: ListTasksRequest) -> TaskListOutputDTO:
        """Execute the task listing workflow.

        Steps:
            1. Validate and resolve input into value objects.
            2. Build a domain-level filter object.
            3. Query the repository for matching tasks.
            4. Map tasks into output DTOs with consistent formatting.

        Args:
            request (ListTasksRequest): Request object containing filter criteria.

        Returns:
            TaskListOutputDTO: List of tasks matching the filters.

        Raises:
            InvalidValueError: If priority, complexity or max_energy is unknown.
            ValidationException: If the user ID or the status is invalid.
        """

        async with self.uow as uow:

            # 1. Validation and resolution of value objects
            try:
                f_user_id: UserId = UserId.from_string(
                    request.user_id, error_msg="Invalid user ID."
                )
            except ValidationException as e:
                raise ValidationException(e) from e

            try:
                f_status: TaskStatus | None = (
                    TaskStatus(request.status) if request.status else None
                )
            except ValueError as e:
                raise ValidationException(f"Invalid status: {request.status}.") from e

            f_priority: Priority | None = (
                Priority.parse(request.priority) if request.priority else None
            )
            f_complexity: TaskComplexity | None = (
                TaskComplexity.parse(request.complexity) if request.complexity else None
            )

            f_parent_id: TaskId | None = None
            if request.parent_id:
                try:
                    f_parent_id = TaskId.from_string(
                        request.parent_id, error_msg="Invalid parent ID."
                    )
                except ValidationException:
                    # Safe behavior: return empty list if parent ID is invalid
                    return TaskListOutputDTO(tasks=[])

            f_context_id: ContextId | None = None
            if request.context_id:
                try:
                    f_context_id = ContextId.from_string(
                        request.context_id, error_msg="Invalid context ID."
                    )
                except ValidationException as e:
                    raise ValidationException(e) from e

            f_ids: list[TaskId] | None = None
            if request.ids:
                try:
                    f_ids = [TaskId.from_string(i) for i in request.ids]
                except ValidationException as e:
                    raise ValidationException(
                        "One or more IDs in the list are invalid."
                    ) from e

            energy_level: EnergyLevel | None = (
                EnergyLevel.parse(request.max_energy) if request.max_energy else None
            )

            # 2. Build complete domain filter (Mapping DTO -> TaskFilter)
            filters: TaskFilter = TaskFilter(
                # Identifiers & Pagination
                user_id=f_user_id,
                parent_id=f_parent_id,
                ids=f_ids,
                limit=request.limit,
                offset=request.offset,
                # Core attributes
                status=f_status,
                # An explicit status wins over hiding the closed ones
                exclude_statuses=(
                    TaskStatus.closed()
                    if not request.include_closed and f_status is None
                    else frozenset()
                ),
                priority=f_priority,
                context_id=f_context_id,
                tags=request.tags,
                # GTD specific
                max_energy_level=energy_level,
                complexity=f_complexity,
                # Behavior flags
                is_blocked=None if request.include_blocked else False,
                is_recurring=request.is_recurring,
                only_roots=request.only_roots,
                # Temporal filters
                due_before=request.due_before,
                due_after=request.due_after,
                created_before=request.created_before,
                created_after=request.created_after,
                updated_before=request.updated_before,
                updated_after=request.updated_after,
            )

            # 3. Query repository
            tasks: list[Task] = await uow.tasks.list(filters)

            # 4. Centralized mapping
            now: datetime = self.clock.now()
            return TaskListOutputDTO(
                tasks=[TaskMapper.to_output(task, now) for task in tasks],
            )
