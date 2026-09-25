from datetime import datetime

from b_domain.entities.context import Context
from b_domain.entities.task import Task
from b_domain.value_objects.identifiers import ContextId
from c_application.dtos.task_dtos import TaskOutputDTO
from c_application.utils import format_task_recurrence


class TaskMapper:
    """Centralized mapper for Task transformations.

    This class decouples the Domain Entities from the Application DTOs.
    """

    @staticmethod
    def to_output(
        task: Task,
        now: datetime,
        occurrences_count: int = 5,
        active_context_id: ContextId | None = None,
        context: Context | None = None,
    ) -> TaskOutputDTO:
        """Maps a Domain Task entity to a TaskOutputDTO for the outside world.

        ``context`` is the task's context entity, when the caller loaded it,
        so the DTO carries its name and icon.
        """
        return TaskOutputDTO(
            id=str(task.id),
            title=str(task.title),
            description=str(task.description),
            status=task.status,
            priority=task.priority.name,
            context_id=str(task.context_id) if task.context_id else None,
            context_name=context.name if context else None,
            context_icon=context.icon if context else None,
            required_energy_level=task.required_energy_level.value,
            due_date=task.due_date.value if task.due_date else None,
            is_overdue=task.due_date.is_overdue(now) if task.due_date else False,
            parent_id=str(task.parent_id) if task.parent_id else None,
            is_blocked=task.is_blocked,
            created_at=task.created_at,
            updated_at=task.updated_at,
            recurrence_display=(
                format_task_recurrence(task.recurrence) if task.recurrence else None
            ),
            next_occurrences=(
                task.recurrence.get_next_n_occurrences(
                    n=occurrences_count, start_from=now
                )
                if task.recurrence
                else []
            ),
            is_in_focus=(
                (task.context_id == active_context_id) if active_context_id else True
            ),
        )
