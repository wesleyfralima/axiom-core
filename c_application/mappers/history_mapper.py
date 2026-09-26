from b_domain.value_objects.task_history import TaskHistoryEntry
from c_application.dtos.task_dtos import FieldChangeDTO, TaskHistoryEntryDTO


def history_entry_to_dto(entry: TaskHistoryEntry) -> TaskHistoryEntryDTO:
    """A history entry for the outside world."""
    return TaskHistoryEntryDTO(
        occurred_at=entry.occurred_at,
        action=str(entry.action),
        changes=[
            FieldChangeDTO(field=c.field, before=c.before, after=c.after)
            for c in entry.changes
        ],
        note=entry.note,
    )
