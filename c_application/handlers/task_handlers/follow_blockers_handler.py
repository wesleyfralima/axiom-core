from b_domain.entities import Task
from b_domain.events.task_events import (
    TaskCancelledEvent,
    TaskCompletedEvent,
    TaskDeletedEvent,
    TaskReopenedEvent,
    TaskRestoredEvent,
    TaskUndoneEvent,
)
from b_domain.ports.providers import ClockProvider
from b_domain.ports.unit_of_work import UnitOfWork
from c_application.use_cases.task.relations import waits_on_open

type BlockerEvent = (
    TaskCompletedEvent
    | TaskCancelledEvent
    | TaskDeletedEvent
    | TaskReopenedEvent
    | TaskRestoredEvent
    | TaskUndoneEvent
)


class FollowBlockersHandler:
    """Keeps "waiting" true to the tasks a task depends on.

    When a task closes (done, cancelled, deleted) the tasks that depend on
    it are free once none of their dependencies is open; when it opens again
    (reopened, restored, a change undone) they wait again. The task itself is
    looked at too: reopened or undone, it may be waiting on others. The
    dependencies stay recorded either way (``relations``).
    """

    def __init__(self, uow: UnitOfWork, clock: ClockProvider):
        """Initialize the handler.

        Args:
            uow (UnitOfWork): Unit of Work instance for transactional consistency.
            clock (ClockProvider): The clock.
        """
        self.uow = uow
        self.clock = clock

    async def handle(self, event: BlockerEvent) -> None:
        """Look again at whether the task and its dependents wait.

        Args:
            event (BlockerEvent): A task closed or opened again.
        """
        async with self.uow:
            touched: list[Task] = await self.uow.tasks.find_tasks_blocked_by(
                event.task_id
            )
            itself: Task | None = await self.uow.tasks.get_by_id(
                event.task_id, event.user_id
            )
            if itself is not None and itself.depends_on and itself.deleted_at is None:
                touched.append(itself)

            now = self.clock.now()
            changed: list[Task] = []
            for task in touched:
                before = task.status
                task.follow_blockers(
                    now, await waits_on_open(self.uow, task.depends_on, task.user_id)
                )
                if task.status != before:
                    changed.append(task)
            if changed:
                await self.uow.tasks.update_many(changed)
