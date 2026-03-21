from uuid import UUID

from a_core.exceptions import ValidationException
from b_domain.entities import Task
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import UserId
from c_application.dtos.task_dtos import TaskByUserRequest


class DeleteTaskUseCase(UseCase[TaskByUserRequest, None]):
    """Use case for deleting a task with partial ID support.

    Ensures that tasks are deleted safely within a transactional context,
    validating ownership and preventing ambiguous prefix deletions.
    """

    async def execute(self, request: TaskByUserRequest) -> None:
        """Execute the task deletion workflow.

        Steps:
            1. Validate the task ID prefix length.
            2. Validate and parse the user ID.
            3. Search tasks by ID prefix scoped to the user.
            4. Handle ambiguous or missing results.
            5. Delete the identified task.

        Args:
            request (TaskByUserRequest): Request object containing task_id_prefix and user_id.

        Raises:
            ValidationException: If the prefix is too short, the user ID is invalid,
            no tasks are found, or multiple ambiguous matches exist.
        """

        task_id_prefix: str = request.task_id_prefix

        # 1. Fail fast: UX safeguard
        if len(task_id_prefix) < 4:
            raise ValidationException("Task ID prefix must have at least 4 characters.")

        try:
            user_id: UserId = UserId(UUID(request.user_id))
        except (ValueError, TypeError):
            raise ValidationException("The provided user_id is invalid.")

        async with self.uow as uow:

            # 2. Search by prefix
            tasks_found: list[Task] = await uow.tasks.find_by_id_prefix(
                id_prefix=task_id_prefix,
                user_id=user_id,
            )

            if not tasks_found:
                raise ValidationException(f"No task found with ID prefix '{task_id_prefix}'.")

            if len(tasks_found) > 1:
                conflicting_ids: str = ", ".join([str(t.id)[:8] for t in tasks_found])
                raise ValidationException(
                    f"Ambiguous ID. Found {len(tasks_found)} tasks: [{conflicting_ids}]. "
                    "Please provide a more specific prefix to avoid deleting the wrong task."
                )

            task_to_delete: Task = tasks_found[0]

            # 3. Safe deletion
            await uow.tasks.delete(task_to_delete.id)
