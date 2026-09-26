from datetime import date, datetime
from typing import Any

from a_core import IdPrefix
from a_core.exceptions import ValidationException
from b_domain.entities import Context, Task, User
from b_domain.entities.user import UserPrefs
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import ContextId, Priority, UserId
from b_domain.value_objects.enums import EnergyLevel
from b_domain.value_objects.recurrences import RecurrenceRule
from c_application.dtos.recurrence_dtos import RecurrenceInputDTO
from c_application.dtos.task_dtos import TaskOutputDTO, UpdateTaskInputDTO
from c_application.mappers.task_mapper import TaskMapper
from c_application.utils import find_context, format_task_recurrence
from c_application.utils.date_input import (
    at_time,
    end_of_day,
    local_today,
    resolve_date_input,
    resolve_horizon,
)
from c_application.utils.recurrence_input import WEEK_STARTS, build_recurrence

PREVIEW_MAX: int = 10
"""The most occurrences an edit's result previews."""


class UpdateTaskUseCase(UseCase[UpdateTaskInputDTO, TaskOutputDTO]):
    """Asynchronous use case for partial task updates.

    Supports partial ID matching and ensures domain rules are respected
    during the update process. Each field update is delegated to the
    Task entity to enforce business rules.
    """

    async def execute(self, request: UpdateTaskInputDTO) -> TaskOutputDTO:
        """Execute the task update workflow.

        Steps:
            1. Validate task ID prefix length.
            2. Validate and parse user ID.
            3. Validate priority if provided.
            4. Retrieve task by prefix scoped to user.
            5. Handle ambiguous or missing results.
            6. Apply partial updates to the task.
            7. Persist the updated task.
            8. Map the entity to an output DTO.

        Args:
            request (UpdateTaskInputDTO): Input data for partial task updates.

        Returns:
            TaskOutputDTO: Output DTO representing the updated task.

        Raises:
            ValidationException: If prefix is too short, user ID is invalid,
                task not found, or multiple ambiguous matches exist.
            InvalidValueError: If priority is unknown.
        """

        # 1. Fail fast: UX safeguard
        try:
            task_id_prefix: IdPrefix = IdPrefix(request.task_id_prefix)
            user_id: UserId = UserId.from_string(
                request.user_id, error_msg="Invalid user ID."
            )
        except ValidationException as e:
            raise ValidationException(e) from e

        priority: Priority | None = (
            Priority.parse(request.priority) if request.priority is not None else None
        )
        energy: EnergyLevel | None = (
            EnergyLevel.parse(request.energy_level)
            if request.energy_level is not None
            else None
        )
        if request.remove_due_date and request.due_date is not None:
            raise ValidationException("Set a new due date or remove it, not both.")
        if request.remove_context and request.context_id is not None:
            raise ValidationException("Pick a context or remove it, not both.")
        if request.remove_recurrence and request.recurrence is not None:
            raise ValidationException("Set a new rule or stop repeating, not both.")

        async with self.uow as uow:
            # 2. Search by prefix scoped to user
            tasks_found: list[Task] = await uow.tasks.find_by_id_prefix(
                id_prefix=task_id_prefix,
                user_id=user_id,
            )

            if not tasks_found:
                raise ValidationException(
                    f"No task found with ID prefix '{request.task_id_prefix}'."
                )

            if len(tasks_found) > 1:
                conflicting_ids: str = ", ".join([str(t.id)[:8] for t in tasks_found])
                raise ValidationException(
                    f"Ambiguous ID. "
                    f"Found {len(tasks_found)} tasks: [{conflicting_ids}]."
                )

            task: Task = tasks_found[0]
            # What the task looks like before, for the history
            names: dict[ContextId, str] = {
                c.id: c.name for c in await uow.contexts.list_by_user(user_id)
            }
            before: dict[str, str | None] = _snapshot(task, names)
            previous: dict[str, Any] = task.snapshot()
            user: User | None = await uow.users.get_by_id(user_id)
            prefs: UserPrefs = user.preferences if user else UserPrefs()

            # 3. Apply partial updates
            now: datetime = self.clock.now()
            # Each update is delegated to the Task entity to enforce domain rules
            if request.title is not None:
                task.rename(now, request.title)

            if request.description is not None:
                task.update_description(now, request.description)

            if priority is not None:
                task.update_priority(now, priority)

            if energy is not None:
                task.update_energy(now, energy)

            if request.estimated_minutes is not None:
                task.update_estimate(now, request.estimated_minutes)

            if request.context_id is not None:
                target: Context = find_context(
                    await uow.contexts.list_by_user(user_id), request.context_id
                )
                task.move_to_context(now, target.id)
            elif request.remove_context:
                task.move_to_context(now, None)

            if request.remove_due_date:
                task.update_due_date(now, None)

            if request.due_date is not None:
                # Keep the task's own kind (floating/fixed) unless the request
                # says otherwise. A floating date keeps its zone; anything else
                # (a fixed date typed as wall-clock time, a task with no due
                # date yet) is read in the user's time zone.
                is_floating: bool = (
                    request.is_floating
                    if request.is_floating is not None
                    else (task.due_date.is_floating if task.due_date else True)
                )
                tz_name: str | None = request.timezone
                if (
                    tz_name is None
                    and is_floating
                    and task.due_date is not None
                    and task.due_date.is_floating
                ):
                    tz_name = task.due_date.timezone
                if tz_name is None:
                    tz_name = prefs.timezone

                # "tomorrow", a date alone (the default due time)…
                new_due: datetime = at_time(
                    resolve_date_input(
                        request.due_date, today=local_today(now, prefs.timezone)
                    ),
                    prefs.default_due_clock,
                )
                task.update_due_date(
                    now, new_due, is_floating=is_floating, tz_name=tz_name
                )

            if request.remove_recurrence:
                task.change_recurrence(now, None)
            elif request.recurrence is not None:
                self._repeat_by(task, request.recurrence, request, prefs, now)

            after: dict[str, str | None] = _snapshot(task, names)
            task.record_edit(
                now,
                {
                    name: (before[name], after[name])
                    for name in before
                    if before[name] != after[name]
                },
                previous=previous,
            )

            # 4. Persistence
            await uow.tasks.update(task)

            context = (
                await uow.contexts.get_by_id(task.context_id, user_id)
                if task.context_id
                else None
            )

        # 5. Return mapped output DTO. Recurring: a preview of what comes
        # next — up to days_ahead, but at least the next one and at most
        # ten, hourly rules included
        horizon: date = resolve_horizon(
            prefs.days_ahead, today=local_today(now, prefs.timezone)
        )
        return TaskMapper.to_output(
            task,
            now,
            occurrences=task.upcoming_occurrences(
                now,
                end_of_day(horizon, prefs.timezone),
                limit=PREVIEW_MAX,
                include_sub_daily=True,
                at_least=1,
            ),
            context=context,
        )

    @staticmethod
    def _repeat_by(
        task: Task,
        recurrence: RecurrenceInputDTO,
        request: UpdateTaskInputDTO,
        prefs: UserPrefs,
        now: datetime,
    ) -> None:
        """Give the task a new rule; its due date stays.

        The rule starts at the due date (or at ``recurrence.start_date``), so
        its time of day is the due date's. A task without a due date gets
        the rule's first occurrence as one, as on create.
        """
        today: date = local_today(now, prefs.timezone)
        is_floating: bool = (
            task.due_date.is_floating
            if task.due_date
            else (request.is_floating if request.is_floating is not None else True)
        )
        tz: str = (
            task.due_date.timezone
            if task.due_date and task.due_date.timezone
            else prefs.timezone
        )
        start: datetime
        if recurrence.start_date is not None:
            start = at_time(
                resolve_date_input(recurrence.start_date, today=today),
                prefs.default_due_clock,
            )
        elif task.due_date is not None:
            start = task.due_date.value
        else:
            start = at_time(today, prefs.default_due_clock)

        rule: RecurrenceRule = build_recurrence(
            recurrence,
            start=start,
            is_floating=is_floating,
            tz=tz,
            today=today,
            week_start=WEEK_STARTS[prefs.week_start],
        )
        if task.due_date is None:
            first: datetime | None = rule.get_next_occurrence()
            if first is not None:
                task.update_due_date(now, first, is_floating=is_floating, tz_name=tz)
        task.change_recurrence(now, rule)


def _snapshot(task: Task, context_names: dict[ContextId, str]) -> dict[str, str | None]:
    """The editable fields as text, to compare before and after an edit."""
    return {
        "title": str(task.title),
        "description": str(task.description) or None,
        "priority": task.priority.name.lower(),
        "energy": task.required_energy_level.name.lower(),
        "context": context_names.get(task.context_id) if task.context_id else None,
        "due": task.due_date.value.isoformat() if task.due_date else None,
        "kind": (
            ("floating" if task.due_date.is_floating else "fixed")
            if task.due_date
            else None
        ),
        "recurrence": format_task_recurrence(task.recurrence),
        "estimate": str(task.estimated_duration_minutes),
    }
