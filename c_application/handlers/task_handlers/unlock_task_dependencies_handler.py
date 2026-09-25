from b_domain.entities import Task
from b_domain.events.task_events import TaskCancelledEvent, TaskCompletedEvent
from b_domain.ports.providers import ClockProvider
from b_domain.ports.unit_of_work import UnitOfWork


class UnlockTaskDependenciesHandler:
    """Domain event handler that reacts to task completion.

    When a task is completed or cancelled, this handler unlocks all tasks
    that depended on it, ensuring that blocked tasks can now proceed: a
    cancelled blocker will never be done, so it no longer holds them back.
    """

    def __init__(self, uow: UnitOfWork, clock: ClockProvider):
        """Initialize the handler with a UnitOfWork.

        Args:
            uow (UnitOfWork): Unit of Work instance for transactional consistency.
            clock (ClockProvider): Clock instance to manage transactional consistency.
        """
        self.uow = uow
        self.clock = clock

    async def handle(self, event: TaskCompletedEvent | TaskCancelledEvent) -> None:
        """Handle a TaskCompletedEvent or a TaskCancelledEvent.

        Steps:
            1. Find tasks that list the completed task in their `depends_on`.
            2. Remove the dependency from each blocked task.
            3. Persist updates in bulk for efficiency.

        Args:
            event (TaskCompletedEvent | TaskCancelledEvent): The domain event
                signaling that the blocker closed.
        """

        async with self.uow:
            # Find tasks that are blocked by the completed task
            blocked_tasks: list[Task] = await self.uow.tasks.find_tasks_blocked_by(
                event.task_id
            )

            if not blocked_tasks:
                return

            # Remove dependency from each blocked task
            for task in blocked_tasks:
                task.remove_dependency(event.task_id, self.clock.now())

            # Bulk update all unlocked tasks
            await self.uow.tasks.update_many(blocked_tasks)
