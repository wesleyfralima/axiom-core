from datetime import datetime

from b_domain.entities import Task
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import UserId
from c_application.dtos import TaskOutputDTO
from c_application.dtos.task_dtos import TaskByUserRequest
from c_application.mappers.task_mapper import TaskMapper
from c_application.utils.task_utils import find_task


class ReopenTaskUseCase(UseCase[TaskByUserRequest, TaskOutputDTO]):
    """Bring a done or cancelled task back to the open ones.

    A reopened recurring occurrence becomes a one-off task (see
    ``Task.reopen``): its series already moved on.
    """

    async def execute(self, request: TaskByUserRequest) -> TaskOutputDTO:
        """Reopen the task.

        Args:
            request (TaskByUserRequest): The task's ID prefix and its owner.

        Returns:
            TaskOutputDTO: The reopened task.

        Raises:
            ValidationException: If the user ID or the prefix is invalid, or
                the prefix is ambiguous.
            EntityNotFound: If the user has no such task.
            InvalidStateTransition: If the task is not done or cancelled.
        """
        user_id: UserId = UserId.from_string(
            request.user_id, error_msg="Invalid user ID."
        )
        now: datetime = self.clock.now()

        async with self.uow as uow:
            task: Task = await find_task(uow, request.task_id_prefix, user_id)
            task.reopen(now)
            await uow.tasks.update(task)

            context = (
                await uow.contexts.get_by_id(task.context_id, user_id)
                if task.context_id
                else None
            )
            return TaskMapper.to_output(task, now, context=context)
