from b_domain.entities import Task
from b_domain.events.task_events import TaskCancelledEvent, TaskCompletedEvent
from b_domain.ports.unit_of_work import UnitOfWork


class CreateRecurringTaskHandler:
    """Domain event handler that generates the next occurrence of a recurring task.

    When a task with recurrence rules is completed or cancelled, this handler
    creates the next scheduled occurrence, ensuring continuity of recurring
    tasks. Cancelling skips one occurrence; only a cancel that ends the series
    stops it.
    """

    def __init__(self, uow: UnitOfWork):
        """Initialize the handler with a UnitOfWork.

        Args:
            uow (UnitOfWork): Unit of Work instance for transactional consistency.
        """
        self.uow = uow

    async def handle(self, event: TaskCompletedEvent | TaskCancelledEvent) -> None:
        """Handle a TaskCompletedEvent or a TaskCancelledEvent.

        Steps:
            1. Load the full task entity to access recurrence rules.
            2. If no recurrence is defined, exit early.
            3. Create the next occurrence based on the completion date.
            4. Estimate duration using the average of past occurrences, when
               there is one.
            5. Persist the new task.

        Args:
            event (TaskCompletedEvent | TaskCancelledEvent): The domain event
                signaling that an occurrence closed.
        """

        if isinstance(event, TaskCancelledEvent) and event.end_series:
            return

        async with self.uow:
            # Retrieve the completed task to access recurrence rules
            task: Task | None = await self.uow.tasks.get_by_id(event.task_id)
            if not task or not task.recurrence:
                return

            # Create the next occurrence based on completion time
            next_task: Task | None = task.create_next_occurrence(event.occurred_at)
            if not next_task:
                return

            # Once past occurrences have a measured average, it becomes the
            # estimate; until then the user's own estimate carries over.
            if task.average_duration_minutes > 0:
                next_task.estimated_duration_minutes = task.average_duration_minutes

            # Persist the new recurring task
            await self.uow.tasks.add(next_task)
