from b_domain.entities import Task
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import UserId
from b_domain.value_objects.task_history import TaskHistoryEntry
from c_application.dtos.task_dtos import (
    FieldChangeDTO,
    TaskByUserRequest,
    TaskHistoryEntryDTO,
    TaskHistoryOutputDTO,
)
from c_application.utils.task_utils import find_task


class GetTaskHistoryUseCase(UseCase[TaskByUserRequest, TaskHistoryOutputDTO]):
    """What happened to a task, oldest first (``axpro task log``)."""

    async def execute(self, request: TaskByUserRequest) -> TaskHistoryOutputDTO:
        """Read one of the user's tasks' history.

        Args:
            request (TaskByUserRequest): The task's ID prefix and its owner.

        Returns:
            TaskHistoryOutputDTO: The entries, oldest first.

        Raises:
            ValidationException: If the user ID or the prefix is invalid, or
                the prefix is ambiguous.
            EntityNotFound: If the user has no such task.
        """
        user_id: UserId = UserId.from_string(
            request.user_id, error_msg="Invalid user ID."
        )
        async with self.uow as uow:
            task: Task = await find_task(uow, request.task_id_prefix, user_id)
            entries: list[TaskHistoryEntry] = await uow.task_history.list_for_task(
                task.id, user_id
            )

        return TaskHistoryOutputDTO(
            task_id=str(task.id),
            title=str(task.title),
            entries=[
                TaskHistoryEntryDTO(
                    occurred_at=entry.occurred_at,
                    action=str(entry.action),
                    changes=[
                        FieldChangeDTO(field=c.field, before=c.before, after=c.after)
                        for c in entry.changes
                    ],
                    note=entry.note,
                )
                for entry in entries
            ],
        )
