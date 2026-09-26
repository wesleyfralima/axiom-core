from b_domain.entities import Task
from b_domain.ports.repositories.filters import TaskFilter
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import TaskId, UserId
from b_domain.value_objects.task_history import TaskHistoryEntry
from c_application.dtos.task_dtos import TaskHistoryOutputDTO, TaskHistoryRequest
from c_application.mappers.history_mapper import history_entry_to_dto
from c_application.utils.task_utils import find_task


class GetTaskHistoryUseCase(UseCase[TaskHistoryRequest, TaskHistoryOutputDTO]):
    """What happened to a task — or to its whole series — oldest first."""

    async def execute(self, request: TaskHistoryRequest) -> TaskHistoryOutputDTO:
        """Read one of the user's tasks' history (or its series').

        Args:
            request (TaskHistoryRequest): The task's ID prefix, its owner and
                whether to span the series (every occurrence, deleted ones
                included).

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
            ids: list[TaskId] = [task.id]
            if request.series and task.series_id is not None:
                members: list[Task] = await uow.tasks.list(
                    TaskFilter(
                        user_id=user_id,
                        series_id=task.series_id,
                        deleted=None,
                        limit=10_000,
                    )
                )
                ids = [m.id for m in members] or ids
            entries: list[TaskHistoryEntry] = await uow.task_history.list_for_tasks(
                ids, user_id
            )

        return TaskHistoryOutputDTO(
            task_id=str(task.id),
            title=str(task.title),
            entries=[history_entry_to_dto(entry) for entry in entries],
            series_size=len(ids),
        )
