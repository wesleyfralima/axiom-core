from datetime import datetime

from b_domain.entities import Task, TimeEntry
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import UserId
from c_application.dtos.task_dtos import CancelTaskInputDTO, TaskStatusChangedOutputDTO
from c_application.mappers.task_mapper import TaskMapper
from c_application.utils.task_utils import find_task


class CancelTaskUseCase(UseCase[CancelTaskInputDTO, TaskStatusChangedOutputDTO]):
    """Cancel a task: the user decided not to do it.

    Side effects go through the ``TaskCancelledEvent``: for a recurring task
    the next occurrence is created (unless the cancel ends the series), and
    tasks that depended on this one are unblocked.
    """

    async def execute(self, request: CancelTaskInputDTO) -> TaskStatusChangedOutputDTO:
        """Cancel the task, stopping its running timers.

        Args:
            request (CancelTaskInputDTO): The task's ID prefix, its owner and
                whether a recurring series ends here.

        Returns:
            TaskStatusChangedOutputDTO: The cancelled task.

        Raises:
            ValidationException: If the user ID or the prefix is invalid, or
                the prefix is ambiguous.
            EntityNotFound: If the user has no such task.
            NotRecurringTaskError: If ``end_series`` is asked of a task that
                does not repeat.
            InvalidStateTransition: If the task is already closed.
        """
        user_id: UserId = UserId.from_string(
            request.user_id, error_msg="Invalid user ID."
        )
        now: datetime = self.clock.now()

        async with self.uow as uow:
            task: Task = await find_task(uow, request.task_id_prefix, user_id)
            task.mark_as_cancelled(now, end_series=request.end_series)
            await uow.tasks.update(task)

            timers: list[TimeEntry] = await uow.time_entries.get_actives_for_task(
                task.id
            )
            if timers:
                for timer in timers:
                    timer.stop(now)
                await uow.time_entries.update_all(timers)

            context = (
                await uow.contexts.get_by_id(task.context_id, user_id)
                if task.context_id
                else None
            )
            return TaskStatusChangedOutputDTO(
                task=TaskMapper.to_output(task, now, context=context),
                series_ended=request.end_series,
            )
