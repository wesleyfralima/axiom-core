from datetime import datetime

from b_domain.entities import Task
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import TaskStatus, UserId
from c_application.dtos.task_dtos import TaskByUserRequest, TaskStatusChangedOutputDTO
from c_application.mappers.task_mapper import TaskMapper
from c_application.utils.task_utils import find_task


class ArchiveTaskUseCase(UseCase[TaskByUserRequest, TaskStatusChangedOutputDTO]):
    """Put a done or cancelled task away for good.

    It leaves even the full task list; only asking for the ``archived``
    status shows it again. There is no way back (but undo). Its closed
    subtasks go with it.
    """

    async def execute(self, request: TaskByUserRequest) -> TaskStatusChangedOutputDTO:
        """Archive the task.

        Args:
            request (TaskByUserRequest): The task's ID prefix and its owner.

        Returns:
            TaskStatusChangedOutputDTO: The archived task.

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
            task.archive(now)
            await uow.tasks.update(task)

            archive_id = task.peek_events()[-1].id
            along: int = 0
            for sub in await uow.tasks.get_subtasks(task.id, limit=10_000):
                if sub.status in (TaskStatus.DONE, TaskStatus.CANCELLED):
                    sub.archive(now, caused_by=archive_id)
                    await uow.tasks.update(sub)
                    along += 1

            context = (
                await uow.contexts.get_by_id(task.context_id, user_id)
                if task.context_id
                else None
            )
            return TaskStatusChangedOutputDTO(
                task=TaskMapper.to_output(task, now, context=context),
                subtasks_along=along,
            )
