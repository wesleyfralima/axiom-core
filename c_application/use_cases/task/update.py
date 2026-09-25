from datetime import datetime

from a_core import IdPrefix
from a_core.exceptions import ValidationException
from b_domain.entities import Task
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import Priority, UserId
from c_application.dtos.task_dtos import TaskOutputDTO, UpdateTaskInputDTO
from c_application.mappers.task_mapper import TaskMapper


class UpdateTaskUseCase(UseCase[UpdateTaskInputDTO, TaskOutputDTO]):
    """Asynchronous use case for partial task updates.

    Supports partial ID matching and ensures domain rules are respected
    during the update process. Each field update is delegated to the
    Task entity to enforce business rules.
    """

    async def execute(self, request: UpdateTaskInputDTO) -> TaskOutputDTO:
        """Execute the task update workflow.

        Steps:
            1. Validate task ID prefix length.
            2. Validate and parse user ID.
            3. Validate priority if provided.
            4. Retrieve task by prefix scoped to user.
            5. Handle ambiguous or missing results.
            6. Apply partial updates to the task.
            7. Persist the updated task.
            8. Map the entity to an output DTO.

        Args:
            request (UpdateTaskInputDTO): Input data for partial task updates.

        Returns:
            TaskOutputDTO: Output DTO representing the updated task.

        Raises:
            ValidationException: If prefix is too short, user ID is invalid,
            priority is invalid, task not found, or multiple ambiguous matches exist.
        """

        # 1. Fail fast: UX safeguard
        try:
            task_id_prefix: IdPrefix = IdPrefix(request.task_id_prefix)
            user_id: UserId = UserId.from_string(
                request.user_id, error_msg="Invalid user ID."
            )
        except ValidationException as e:
            raise ValidationException(e) from e

        try:
            priority: Priority = Priority(request.priority)
        except ValueError as e:
            raise ValidationException(f"Invalid priority: {request.priority}") from e

        async with self.uow as uow:
            # 2. Search by prefix scoped to user
            tasks_found: list[Task] = await uow.tasks.find_by_id_prefix(
                id_prefix=task_id_prefix,
                user_id=user_id,
            )

            if not tasks_found:
                raise ValidationException(
                    f"No task found with ID prefix '{request.task_id_prefix}'."
                )

            if len(tasks_found) > 1:
                conflicting_ids: str = ", ".join([str(t.id)[:8] for t in tasks_found])
                raise ValidationException(
                    f"Ambiguous ID. "
                    f"Found {len(tasks_found)} tasks: [{conflicting_ids}]."
                )

            task: Task = tasks_found[0]

            # 3. Apply partial updates
            now: datetime = self.clock.now()
            # Each update is delegated to the Task entity to enforce domain rules
            if request.title is not None:
                task.rename(now, request.title)

            if request.description is not None:
                task.update_description(now, request.description)

            if request.priority is not None:
                task.update_priority(now, priority)

            if request.due_date is not None:
                # Timezone handling could be added here if needed
                task.update_due_date(now, request.due_date)

            # 4. Persistence
            await uow.tasks.update(task)

        # 5. Return mapped output DTO
        return TaskMapper.to_output(task, now)
