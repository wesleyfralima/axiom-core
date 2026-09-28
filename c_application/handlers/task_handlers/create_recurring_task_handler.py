from b_domain.entities import Task, User, UserPrefs
from b_domain.entities.task import subtask_copy_id
from b_domain.events.task_events import TaskCancelledEvent, TaskCompletedEvent
from b_domain.ports.unit_of_work import UnitOfWork
from b_domain.value_objects import TaskId
from c_application.use_cases.task.relations import (
    shifted_due,
    subtasks_minutes,
    waits_on_open,
)
from c_application.utils.work_calendar import use_work_calendar


class CreateRecurringTaskHandler:
    """Domain event handler that generates the next occurrence of a recurring task.

    When a task with recurrence rules is completed or cancelled, this handler
    creates the next scheduled occurrence, ensuring continuity of recurring
    tasks. Cancelling skips one occurrence; only a cancel that ends the series
    stops it. The next occurrence brings the subtasks along, open again: the
    ones the parent has now (added ones included, deleted ones gone), each as
    far before the parent's due date as it was. A subtask never repeats on
    its own.
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
            4. Skip it if that occurrence is already there (its ID is the
               same on every device); bring it back if an undo took it away.
            5. Estimate duration using the average of past occurrences, when
               there is one.
            6. Persist the new task.

        Args:
            event (TaskCompletedEvent | TaskCancelledEvent): The domain event
                signaling that an occurrence closed.
        """

        if isinstance(event, TaskCancelledEvent) and event.end_series:
            return

        async with self.uow:
            # Retrieve the completed task to access recurrence rules
            task: Task | None = await self.uow.tasks.get_by_id(event.task_id)
            if not task or not task.recurrence or task.parent_id is not None:
                return

            # "The Nth business day" counts the user's business days
            if task.recurrence.uses_business_days:
                user: User | None = await self.uow.users.get_by_id(task.user_id)
                prefs: UserPrefs = user.preferences if user else UserPrefs()
                await use_work_calendar(self.uow, task.user_id, prefs, [task])

            # Create the next occurrence based on completion time
            # Linked to the change that made it: undo removes it with that one
            next_task: Task | None = task.create_next_occurrence(
                event.occurred_at, caused_by=event.id
            )
            if not next_task:
                return

            # Its ID comes from the series and the date, so the row may be
            # there already: made by another device, or before a reopen —
            # then there is nothing to add; or taken away by an undo of
            # this completion — then it comes back, as new
            existing: Task | None = await self.uow.tasks.get_by_id(next_task.id)
            if existing is not None and existing.deleted_at is None:
                return

            # Once past occurrences have a measured average, it becomes the
            # estimate; until then the user's own estimate carries over.
            if task.average_duration_minutes > 0:
                next_task.estimated_duration_minutes = task.average_duration_minutes

            # Persist the new recurring task
            if existing is None:
                await self.uow.tasks.add(next_task)
            else:
                existing.come_back_as(next_task)
                await self.uow.tasks.update(existing)

            await self._bring_subtasks(task, existing or next_task, event)

    async def _bring_subtasks(
        self,
        task: Task,
        next_task: Task,
        event: TaskCompletedEvent | TaskCancelledEvent,
    ) -> None:
        """Copy ``task``'s subtasks under its next occurrence, open.

        Each copy's ID comes from the new parent and the subtask (the same
        on every device); one already there is left, one an undo took away
        comes back. A dependency between siblings points to the sibling's
        copy.
        """
        subtasks: list[Task] = await self.uow.tasks.get_subtasks(task.id, limit=10_000)
        if not subtasks:
            return
        copies: dict[TaskId, TaskId] = {
            sub.id: subtask_copy_id(next_task.id, sub.id) for sub in subtasks
        }
        made: list[Task] = []
        for sub in subtasks:
            depends_on: set[TaskId] = {copies.get(ref, ref) for ref in sub.depends_on}
            outside: set[TaskId] = {ref for ref in depends_on if ref in sub.depends_on}
            copy: Task = sub.copy_under(
                event.occurred_at,
                next_task,
                shifted_due(sub.due_date, task.due_date, next_task.due_date),
                depends_on,
                # A sibling's copy is open; an outside task, as it is
                waiting=len(outside) < len(depends_on)
                or await waits_on_open(self.uow, outside, task.user_id),
                caused_by=event.id,
            )
            existing: Task | None = await self.uow.tasks.get_by_id(copy.id)
            if existing is not None and existing.deleted_at is None:
                continue
            if existing is None:
                await self.uow.tasks.add(copy)
            else:
                existing.come_back_as(copy)
                await self.uow.tasks.update(existing)
            made.append(copy)
        # The copies are open again: the new parent covers them all (it is
        # new — no edit to record)
        total: int = await subtasks_minutes(self.uow, next_task, made)
        if total > next_task.estimated_duration_minutes:
            next_task.update_estimate(event.occurred_at, total)
            await self.uow.tasks.update(next_task)
