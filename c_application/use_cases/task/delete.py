from dataclasses import dataclass

from a_core import DTO, EntityNotFound, IdPrefix
from a_core.exceptions import AmbiguousIdentifierError
from b_domain.entities import Task
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import UserId


@dataclass(frozen=True, kw_only=True)
class DeleteTaskInputDTO(DTO):
    """Data transfer object for task deletion requests.

    Attributes:
        task_id_prefix (str): The ID or prefix of the task to be deleted.
        user_id (str): The unique identifier of the user requesting deletion.
    """

    task_id_prefix: str
    user_id: str


@dataclass(frozen=True, kw_only=True)
class DeleteTaskOutputDTO(DTO):
    """Data transfer object for task deletion results.

    Attributes:
        success (bool): Indicates whether the deletion was successful.
        task_id (str): The unique identifier of the deleted task.
    """

    success: bool
    task_id: str


class DeleteTaskUseCase(UseCase[DeleteTaskInputDTO, DeleteTaskOutputDTO]):
    """Use case for deleting a task with partial ID support.

    Ensures that tasks are deleted safely within a transactional context,
    validating ownership and preventing ambiguous prefix deletions.
    """

    async def execute(self, request: DeleteTaskInputDTO) -> DeleteTaskOutputDTO:
        """Execute the task deletion workflow.

        Steps:
            1. Validate the task ID prefix length.
            2. Validate and parse the user ID.
            3. Search tasks by ID prefix scoped to the user.
            4. Handle ambiguous or missing results.
            5. Delete the identified task.

        Args:
            request (DeleteTaskInputDTO): Request object containing
                task_id_prefix and user_id.

        Raises:
            ValidationException: If the prefix is too short, the user ID is invalid,
            no tasks are found, or multiple ambiguous matches exist.
        """

        # 1. Fail fast: UX safeguard (IdPrefix and
        # UserId will raise ValidationException)
        task_id_prefix: IdPrefix = IdPrefix(request.task_id_prefix)
        user_id: UserId = UserId.from_string(
            request.user_id, error_msg="Invalid user ID."
        )

        async with self.uow as uow:

            # 2. Search by prefix
            tasks_found: list[Task] = await uow.tasks.find_by_id_prefix(
                id_prefix=task_id_prefix,
                user_id=user_id,
            )

            if not tasks_found:
                raise EntityNotFound(entity_name="Task", identifier=str(task_id_prefix))

            if len(tasks_found) > 1:
                conflicting_ids: list[str] = [str(t.id)[:8] for t in tasks_found]
                raise AmbiguousIdentifierError(
                    resource_name="tasks",
                    identifier=str(task_id_prefix),
                    matches=conflicting_ids,
                )

            task_to_delete: Task = tasks_found[0]

            # 3. Safe deletion
            await uow.tasks.delete(task_to_delete.id)

            return DeleteTaskOutputDTO(success=True, task_id=str(task_to_delete.id))
