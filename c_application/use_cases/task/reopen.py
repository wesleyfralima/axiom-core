from datetime import datetime

from a_core.exceptions import InvalidStateTransition
from b_domain.entities import Task
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import TaskStatus, UserId
from c_application.dtos.task_dtos import TaskByUserRequest, TaskStatusChangedOutputDTO
from c_application.mappers.task_mapper import TaskMapper
from c_application.use_cases.task.relations import closed_along
from c_application.utils.task_utils import find_task


class ReopenTaskUseCase(UseCase[TaskByUserRequest, TaskStatusChangedOutputDTO]):
    """Bring a done or cancelled task back to the open ones.

    A reopened recurring occurrence becomes a one-off task (see
    ``Task.reopen``): its series already moved on. A subtask of a closed
    parent opens the parent too (the whole is not done while a part is not);
    a reopened parent brings back the subtasks it closed along with it (one
    closed before, or by itself, stays closed).
    """

    async def execute(self, request: TaskByUserRequest) -> TaskStatusChangedOutputDTO:
        """Reopen the task.

        Args:
            request (TaskByUserRequest): The task's ID prefix and its owner.

        Returns:
            TaskStatusChangedOutputDTO: The reopened task.

        Raises:
            ValidationException: If the user ID or the prefix is invalid, or
                the prefix is ambiguous.
            EntityNotFound: If the user has no such task.
            InvalidStateTransition: If the task is not done or cancelled, or
                it is a subtask of an archived task.
        """
        user_id: UserId = UserId.from_string(
            request.user_id, error_msg="Invalid user ID."
        )
        now: datetime = self.clock.now()

        async with self.uow as uow:
            task: Task = await find_task(uow, request.task_id_prefix, user_id)
            parent: Task | None = (
                await uow.tasks.get_by_id(task.parent_id, user_id)
                if task.parent_id
                else None
            )
            if parent is not None and parent.status is TaskStatus.ARCHIVED:
                raise InvalidStateTransition(
                    f"Its parent '{parent.title}' is archived: a part of it "
                    "cannot be open."
                )
            along: list[Task] = await closed_along(uow, task, user_id)
            task.reopen(now)
            await uow.tasks.update(task)
            reopen_id = task.peek_events()[-1].id
            for sub in along:
                sub.reopen(now, caused_by=reopen_id)
                await uow.tasks.update(sub)

            reopened: str | None = None
            if parent is not None and parent.status.is_closed:
                parent.reopen(now, caused_by=reopen_id)
                await uow.tasks.update(parent)
                reopened = str(parent.title)

            context = (
                await uow.contexts.get_by_id(task.context_id, user_id)
                if task.context_id
                else None
            )
            return TaskStatusChangedOutputDTO(
                task=TaskMapper.to_output(task, now, context=context),
                parent_reopened=reopened,
                subtasks_reopened=len(along),
            )
