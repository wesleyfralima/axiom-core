from datetime import datetime
from typing import Any

from b_domain.entities.context import Context
from b_domain.entities.task import Task
from b_domain.value_objects.identifiers import ContextId
from c_application.dtos.task_dtos import TaskOutputDTO
from c_application.mappers.recurrence_mapper import RecurrenceMapper
from c_application.utils import format_task_recurrence


class TaskMapper:
    """Centralized mapper for Task transformations.

    This class decouples the Domain Entities from the Application DTOs.
    """

    @staticmethod
    def to_output(
        task: Task,
        now: datetime,
        occurrences_until: datetime | None = None,
        occurrences: list[datetime] | None = None,
        time_spent_minutes: int = 0,
        running_since: datetime | None = None,
        active_context_id: ContextId | None = None,
        context: Context | None = None,
        parent_title: str | None = None,
        relations: dict[str, Any] | None = None,
        parent: Task | None = None,
    ) -> TaskOutputDTO:
        """Maps a Domain Task entity to a TaskOutputDTO for the outside world.

        ``context`` is the task's context entity, when the caller loaded it,
        so the DTO carries its name and icon. ``occurrences_until`` (aware)
        fills ``next_occurrences`` with the occurrences projected up to it;
        ``occurrences`` gives them ready (they win). ``relations`` are the
        fields ``relations_of`` fills (parent, subtasks, dependencies).
        ``parent`` is a subtask's parent, when the caller loaded it: one due
        with it shares its deadline.
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
            is_overdue=task.is_overdue(now, parent),
            strict_due=task.strict_due,
            snoozed_from=task.snoozed_from.value if task.snoozed_from else None,
            took_minutes=task.took_minutes,
            deadline=task.deadline(parent),
            parent_id=str(task.parent_id) if task.parent_id else None,
            parent_title=parent_title,
            is_blocked=task.is_blocked,
            created_at=task.created_at,
            completed_at=task.completed_at,
            series_id=str(task.series_id) if task.series_id else None,
            estimated_minutes=task.estimated_duration_minutes,
            tags=sorted(task.tags),
            time_spent_minutes=time_spent_minutes,
            running_since=running_since,
            updated_at=task.updated_at,
            recurrence_display=(
                format_task_recurrence(task.recurrence) if task.recurrence else None
            ),
            recurrence=(
                RecurrenceMapper.to_output(task.recurrence) if task.recurrence else None
            ),
            next_occurrences=(
                occurrences
                if occurrences is not None
                else task.upcoming_occurrences(now, occurrences_until)
                if occurrences_until
                else []
            ),
            is_in_focus=(
                (task.context_id == active_context_id) if active_context_id else True
            ),
            **(relations or {}),
        )
