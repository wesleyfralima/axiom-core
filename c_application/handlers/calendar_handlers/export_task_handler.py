from b_domain.entities import Task, User
from b_domain.events.task_events import TaskCreatedEvent
from b_domain.ports.providers import ClockProvider
from b_domain.ports.providers.calendar_provider import CalendarEventInput, CalendarProvider, CalendarEventOutput
from b_domain.ports.unity_of_work import UnitOfWork


class ExportTaskToCalendarHandler:
    """Domain event handler that exports newly created tasks to an external calendar.

    Reacts to TaskCreatedEvent by:
      1. Retrieving the task.
      2. Checking idempotency (already exported).
      3. Applying business rules (only tasks with due dates or recurrence).
      4. Creating the event in the external calendar provider.
      5. Persisting the external calendar ID back into the task.
    """

    def __init__(self, uow: UnitOfWork, calendar_provider: CalendarProvider, clock_provider: ClockProvider):
        """Initialize the handler.

        Args:
            uow (UnitOfWork): Unit of Work for transactional consistency.
            calendar_provider (CalendarProvider): External calendar integration.
            clock_provider (ClockProvider): Clock integration.
        """
        self.uow = uow
        self.clock = clock_provider
        self.calendar_provider = calendar_provider

    async def handle(self, event: TaskCreatedEvent) -> None:
        """Handle a TaskCreatedEvent by exporting the task to a calendar.

        Args:
            event (TaskCreatedEvent): The domain event signaling task creation.
        """

        async with self.uow:

            # 1.1. Retrieve the task entity
            task: Task = await self.uow.tasks.get_by_id(event.task_id)
            if not task:
                return

            # 1.2. Get user calendar information
            user: User = await self.uow.users.get_by_id(task.user_id)
            if not user:
                return

            calendar_id: str = user.preferences.external_calendar_id
            if not calendar_id:
                return

            # 2. Idempotency check: skip if already exported
            if task.has_calendar_event:
                return

            # 3. Business rule: only export if due date OR recurrence exists
            if not (task.due_date.value or task.recurrence):
                return

            # Build calendar event input from task
            event_input: CalendarEventInput = CalendarEventInput.from_task(task)

        # 4. External call: create event in external calendar
        external_event: CalendarEventOutput = await self.calendar_provider.create_event(
            calendar_id=calendar_id,
            event_data=event_input,
        )

        # 5. Persist result: mark task as exported with external ID
        async with self.uow:

            task = await self.uow.tasks.get_by_id(event.task_id)

            # Double-check to avoid race condition (another handler may have updated)
            if task.has_calendar_event:
                return

            task.mark_as_synced(
                now=self.clock.now(),
                external_id=external_event.id,
                calendar_id=external_event.calendar_id,
                link=external_event.html_link,
            )

            await self.uow.commit()
