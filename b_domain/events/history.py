"""Domain events → task history entries (the unit of work records them)."""

from a_core import DomainEvent
from b_domain.events.task_events import (
    TaskArchivedEvent,
    TaskCancelledEvent,
    TaskCompletedEvent,
    TaskCreatedEvent,
    TaskDeletedEvent,
    TaskEditedEvent,
    TaskReopenedEvent,
)
from b_domain.value_objects.task_history import (
    FieldChange,
    TaskAction,
    TaskHistoryEntry,
)

_ACTIONS: dict[type[DomainEvent], TaskAction] = {
    TaskCreatedEvent: TaskAction.CREATED,
    TaskEditedEvent: TaskAction.EDITED,
    TaskCompletedEvent: TaskAction.COMPLETED,
    TaskCancelledEvent: TaskAction.CANCELLED,
    TaskReopenedEvent: TaskAction.REOPENED,
    TaskArchivedEvent: TaskAction.ARCHIVED,
    TaskDeletedEvent: TaskAction.DELETED,
}


def history_entry(event: DomainEvent) -> TaskHistoryEntry | None:
    """The history entry an event means, or None for events of other kinds.

    Args:
        event (DomainEvent): Any event a tracked entity recorded.

    Returns:
        TaskHistoryEntry | None: The entry, when the event is about a task
        and says whose it is.
    """
    action: TaskAction | None = _ACTIONS.get(type(event))
    task_id = getattr(event, "task_id", None)
    user_id = getattr(event, "user_id", None)
    if action is None or task_id is None or user_id is None:
        return None

    changes: tuple[FieldChange, ...] = ()
    if isinstance(event, TaskEditedEvent):
        changes = tuple(
            FieldChange(field=name, before=values[0], after=values[1])
            for name, values in event.changes.items()
        )
    note: str | None = None
    if isinstance(event, TaskCancelledEvent) and event.end_series:
        note = "The series ends here."
    if isinstance(event, TaskDeletedEvent):
        note = event.title

    return TaskHistoryEntry(
        task_id=task_id,
        user_id=user_id,
        occurred_at=event.occurred_at,
        action=action,
        changes=changes,
        note=note,
    )
