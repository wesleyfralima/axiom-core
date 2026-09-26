from datetime import date, datetime

from a_core import IdPrefix
from a_core.exceptions import ValidationException
from b_domain.entities import Task, User
from b_domain.entities.user import UserPrefs
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import UserId
from c_application.dtos import TaskOutputDTO
from c_application.dtos.task_dtos import GetTaskRequest
from c_application.mappers.task_mapper import TaskMapper
from c_application.utils.date_input import end_of_day, local_today, resolve_horizon


class GetTaskUseCase(UseCase[GetTaskRequest, TaskOutputDTO]):
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

        # 1. UX validation (prefix matching)
        try:
            task_id_prefix: IdPrefix = IdPrefix(request.task_id_prefix)
            user_id: UserId = UserId.from_string(
                request.user_id, error_msg="Invalid user ID."
            )
        except ValidationException as e:
            raise ValidationException(e) from e

        async with self.uow as uow:
            # 2. Search with prefix support, scoped by user_id
            tasks_found: list[Task] = await uow.tasks.find_by_id_prefix(
                id_prefix=task_id_prefix,
                user_id=user_id,
            )

            if not tasks_found:
                raise ValidationException(
                    f"No task found with ID prefix '{task_id_prefix}'."
                )

            if len(tasks_found) > 1:
                conflicting_ids: str = ", ".join([str(t.id)[:8] for t in tasks_found])
                raise ValidationException(
                    f"Ambiguous ID. "
                    f"Found {len(tasks_found)} tasks: [{conflicting_ids}]. "
                    "Please provide a more specific prefix."
                )

            task: Task = tasks_found[0]

            # 3. Centralized mapping
            # TaskMapper handles status, priority, and upcoming occurrences
            context = (
                await uow.contexts.get_by_id(task.context_id, user_id)
                if task.context_id
                else None
            )
            # Recurring: the occurrences ahead, up to the horizon asked for
            # (or the user's days_ahead)
            user: User | None = await uow.users.get_by_id(user_id)
            prefs: UserPrefs = user.preferences if user else UserPrefs()
            now: datetime = self.clock.now()
            horizon: date = resolve_horizon(
                request.ahead if request.ahead is not None else prefs.days_ahead,
                today=local_today(now, prefs.timezone),
            )
            return TaskMapper.to_output(
                task,
                now,
                occurrences_until=end_of_day(horizon, prefs.timezone),
                context=context,
            )
