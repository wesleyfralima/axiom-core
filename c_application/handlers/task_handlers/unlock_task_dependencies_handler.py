from b_domain.entities import Task
from b_domain.events.task_events import TaskCompletedEvent
from b_domain.ports.providers import ClockProvider
from b_domain.ports.unit_of_work import UnitOfWork


class UnlockTaskDependenciesHandler:
    """Domain event handler that reacts to task completion.

    When a task is completed, this handler unlocks all tasks that
    depended on it, ensuring that blocked tasks can now proceed.
    """

    def __init__(self, uow: UnitOfWork, clock: ClockProvider):
        """Initialize the handler with a UnitOfWork.

        Args:
            uow (UnitOfWork): Unit of Work instance for transactional consistency.
            clock (ClockProvider): Clock instance to manage transactional consistency.
        """
        self.uow = uow
        self.clock = clock

    async def handle(self, event: TaskCompletedEvent) -> None:
        """Handle a TaskCompletedEvent.

        Steps:
            1. Find tasks that list the completed task in their `depends_on`.
            2. Remove the dependency from each blocked task.
            3. Persist updates in bulk for efficiency.

        Args:
            event (TaskCompletedEvent): The domain event signaling task completion.
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
