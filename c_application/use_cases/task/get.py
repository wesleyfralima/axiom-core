from uuid import UUID

from a_core.exceptions import ValidationException
from b_domain.entities import Task
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import UserId
from c_application.dtos import TaskOutputDTO
from c_application.dtos.task_dtos import GetTaskRequest
from c_application.mappers.task_mapper import TaskMapper


class GetTaskUseCase(UseCase[None, TaskOutputDTO]):
    """Use case for retrieving the details of a specific task.

    Supports partial ID matching (prefix-based search) and centralizes
    mapping via TaskMapper to ensure consistent output formatting.
    """

    async def execute(self, request: GetTaskRequest) -> TaskOutputDTO:
        """Execute the task retrieval workflow.

        Steps:
            1. Validate the task ID prefix.
            2. Validate and parse the user ID.
            3. Search tasks by ID prefix scoped to the user.
            4. Handle ambiguous or missing results.
            5. Map the task entity to an output DTO.

        Args:
            request (GetTaskRequest): Request object containing task ID prefix,
                user ID, and number of occurrences to include.

        Returns:
            TaskOutputDTO: Output DTO representing the retrieved task.

        Raises:
            ValidationException: If the prefix is too short, the user ID is invalid,
            no tasks are found, or multiple ambiguous matches exist.
        """

        task_id_prefix: str = request.task_id_prefix
        n_occurrences: int = request.n_occurrences

        # 1. UX validation (prefix matching)
        if len(task_id_prefix) < 4:
            raise ValidationException("Task ID prefix must have at least 4 characters.")

        try:
            user_id: UserId = UserId(UUID(request.user_id))
        except (ValueError, TypeError):
            raise ValidationException("The provided user_id is invalid.")

        async with self.uow:
            # 2. Search with prefix support, scoped by user_id
            tasks_found: list[Task] = await self.uow.tasks.find_by_id_prefix(
                id_prefix=task_id_prefix,
                user_id=user_id
            )

            if not tasks_found:
                raise ValidationException(f"No task found with ID prefix '{task_id_prefix}'.")

            if len(tasks_found) > 1:
                conflicting_ids: str = ", ".join([str(t.id)[:8] for t in tasks_found])
                raise ValidationException(
                    f"Ambiguous ID. Found {len(tasks_found)} tasks: [{conflicting_ids}]. "
                    "Please provide a more specific prefix."
                )

            task: Task = tasks_found[0]

            # 3. Centralized mapping
            # TaskMapper handles status, priority, and upcoming occurrences
            return TaskMapper.to_output(task, self.clock.now(), n_occurrences)
