from datetime import datetime
from typing import List
from uuid import UUID

from a_core.exceptions import EntityNotFound, ValidationException
from b_domain.entities import Task
from b_domain.ports.repositories import TaskFilter
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import Priority, TaskId, TaskStatus, UserId
from c_application.dtos.task_dtos import ListTasksRequest, TaskListOutputDTO
from c_application.mappers.task_mapper import TaskMapper


class ListTasksUseCase(UseCase[ListTasksRequest, TaskListOutputDTO]):
    """Use case for listing tasks with filtering and domain mapping.

    This use case applies filters such as status, priority, parent ID,
    tags, and root-only flag, then maps the results into output DTOs.
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
            EntityNotFound: If status or priority values are invalid.
            ValidationException: If the user ID is invalid.
        """

        async with self.uow as uow:

            # 1. Validation and resolution of value objects
            try:
                f_status: TaskStatus = TaskStatus(request.status) if request.status else None
            except ValueError:
                raise EntityNotFound(entity_name="TaskStatus", identifier=request.status)

            try:
                f_priority: Priority = Priority(request.priority) if request.priority else None
            except ValueError:
                raise EntityNotFound(entity_name="Priority", identifier=request.priority)

            try:
                f_user_id: UserId = UserId(UUID(request.user_id))
            except (ValueError, TypeError):
                raise ValidationException("The provided user_id is invalid.")

            f_parent_id: TaskId | None = None
            if request.parent_id:
                try:
                    f_parent_id = TaskId(UUID(request.parent_id))
                except (ValueError, TypeError):
                    # Safe behavior: return empty list if parent ID is invalid
                    return TaskListOutputDTO(tasks=[])

            # 2. Build domain filter
            filters: TaskFilter = TaskFilter(
                user_id=f_user_id,
                status=f_status,
                priority=f_priority,
                parent_id=f_parent_id,
                tags=request.tags,
                only_roots=request.only_roots,
            )

            # 3. Query repository
            tasks: List[Task] = await uow.tasks.list(filters)

            # 4. Centralized mapping
            now: datetime = self.clock.now()
            return TaskListOutputDTO(
                tasks=[TaskMapper.to_output(task, now) for task in tasks],
            )
