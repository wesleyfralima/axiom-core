from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime
from typing import Any

from a_core import IdPrefix, UniqueId
from a_core.exceptions import ValidationException
from b_domain.entities import Context, Task, User
from b_domain.entities.user import UserPrefs
from b_domain.events.task_events import TaskEditedEvent
from b_domain.ports.unit_of_work import UnitOfWork
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import ContextId, Priority, TaskId, UserId
from b_domain.value_objects.dates import DueDate
from b_domain.value_objects.enums import EnergyLevel
from b_domain.value_objects.recurrences import RecurrenceRule
from b_domain.value_objects.texts import normalize_tags
from b_domain.value_objects.work_calendar import WorkCalendar, weekdays_only
from c_application.dtos.recurrence_dtos import RecurrenceInputDTO
from c_application.dtos.task_dtos import TaskOutputDTO, UpdateTaskInputDTO
from c_application.mappers.task_mapper import TaskMapper
from c_application.use_cases.task.relations import (
    check_can_be_subtask,
    check_dependency,
    check_family,
    check_family_links,
    check_parent,
    check_takes_subtasks,
    cover_subtasks,
    fit_under,
    minutes_text,
    pull_subtasks,
    relations_of,
    subtasks_minutes,
    waits_on_open,
)
from c_application.utils import find_context, format_task_recurrence
from c_application.utils.date_input import (
    at_time,
    end_of_day,
    local_today,
    resolve_date_input,
    resolve_horizon,
)
from c_application.utils.recurrence_input import WEEK_STARTS, build_recurrence
from c_application.utils.task_utils import find_task
from c_application.utils.work_calendar import load_work_calendar, use_work_calendar

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
        if request.remove_parent and request.parent_id is not None:
            raise ValidationException("Pick a parent or remove it, not both.")

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
            before: dict[str, str | None] = {
                **_snapshot(task, names),
                **await _relations_text(uow, task, user_id),
            }
            previous: dict[str, Any] = task.snapshot()
            old_due: DueDate | None = task.due_date
            user: User | None = await uow.users.get_by_id(user_id)
            prefs: UserPrefs = user.preferences if user else UserPrefs()
            # Business days are the user's, for the rule it has or gets
            calendar: WorkCalendar | None = await use_work_calendar(
                uow, user_id, prefs, [task]
            )
            if (
                calendar is None
                and request.recurrence is not None
                and request.recurrence.nth_business_day is not None
            ):
                calendar = await load_work_calendar(uow, user_id, prefs)

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

            if request.strict_due is not None and request.strict_due != task.strict_due:
                task.set_strict_due(now, request.strict_due)

            if request.tags is not None or request.add_tags or request.remove_tags:
                tags: frozenset[str] = (
                    normalize_tags(request.tags)
                    if request.tags is not None
                    else task.tags
                )
                tags = (tags | normalize_tags(request.add_tags)) - normalize_tags(
                    request.remove_tags
                )
                if tags != task.tags:
                    task.set_tags(now, tags)

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

            kept_missed: bool = (
                task.recurrence.keep_missed if task.recurrence is not None else False
            )
            if request.remove_recurrence:
                task.change_recurrence(now, None)
            elif request.recurrence is not None:
                self._repeat_by(
                    task,
                    request.recurrence,
                    request,
                    prefs,
                    now,
                    calendar.is_business_day if calendar else weekdays_only,
                )
            # A habit or a bill: as asked, else as it was (a new rule too)
            keep_missed: bool | None = (
                request.keep_missed
                if request.keep_missed is not None
                else (kept_missed if request.recurrence is not None else None)
            )
            if keep_missed is not None:
                if task.recurrence is None:
                    raise ValidationException(
                        f"'{task.title}' does not repeat: only a recurring task "
                        "keeps or skips its missed occurrences."
                    )
                if task.recurrence.keep_missed != keep_missed:
                    task.change_recurrence(
                        now, replace(task.recurrence, keep_missed=keep_missed)
                    )

            # Parent and dependencies: never a loop (a task under its own
            # subtask, two tasks waiting on each other)
            if request.parent_id is not None:
                new_parent: Task = await find_task(uow, request.parent_id, user_id)
                await check_parent(uow, task, new_parent, user_id)
                check_takes_subtasks(new_parent)
                await check_can_be_subtask(uow, task)
                task.move_under(now, new_parent.id)
            elif request.remove_parent:
                task.move_under(now, None)

            # A subtask stays within its parent: what was asked is refused
            # beyond it; a task just moved under it is brought within it
            notes: list[str] = []
            parent: Task | None = (
                await uow.tasks.get_by_id(task.parent_id, user_id)
                if task.parent_id
                else None
            )
            due_asked: bool = request.due_date is not None or request.remove_due_date
            if parent is not None:
                if request.recurrence is not None:
                    raise ValidationException(
                        "A subtask does not repeat: its parent does, and brings "
                        "it along."
                    )
                if request.parent_id is not None or due_asked or priority is not None:
                    notes += fit_under(
                        now,
                        task,
                        parent,
                        due_asked=due_asked,
                        priority_asked=priority is not None,
                    )
            # A parent takes at least as long as its subtasks together
            if request.estimated_minutes is not None:
                total: int = await subtasks_minutes(uow, task)
                if request.estimated_minutes < total:
                    raise ValidationException(
                        f"'{task.title}' cannot take less than its subtasks "
                        f"together: {minutes_text(total)}."
                    )

            if request.add_dependencies or request.remove_dependencies:
                depends_on: set[TaskId] = set(task.depends_on)
                for ref in request.add_dependencies:
                    blocker: Task = await find_task(uow, ref, user_id)
                    await check_dependency(uow, task, blocker, user_id)
                    check_family(task, blocker)
                    depends_on.add(blocker.id)
                for ref in request.remove_dependencies:
                    # Among its own dependencies (a deleted one included)
                    prefix: IdPrefix = IdPrefix(ref)
                    matched: set[TaskId] = {d for d in depends_on if prefix.matches(d)}
                    if not matched:
                        raise ValidationException(
                            f"'{task.title}' does not depend on a task '{ref}'."
                        )
                    depends_on -= matched
                task.set_dependencies(
                    now,
                    depends_on,
                    waiting=await waits_on_open(uow, depends_on, user_id),
                )
            # Moved: its dependencies (those left) stay within its new family
            if request.parent_id is not None or request.remove_parent:
                await check_family_links(uow, task, user_id)

            after: dict[str, str | None] = {
                **_snapshot(task, names),
                **await _relations_text(uow, task, user_id),
            }
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

            # What the edit changes on its own, undone with it: the parent's
            # open subtasks follow it; a subtask's parent covers its estimate
            events = task.peek_events()
            edit_id: UniqueId | None = (
                events[-1].id
                if events and isinstance(events[-1], TaskEditedEvent)
                else None
            )
            if edit_id is not None and parent is None:
                notes += await pull_subtasks(uow, now, task, old_due, edit_id)
            if edit_id is not None and parent is not None:
                note: str | None = await cover_subtasks(
                    uow, now, parent, [task], caused_by=edit_id
                )
                notes += [note] if note else []
            relations: dict[str, Any] = await relations_of(uow, task, user_id)

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
        return replace(
            TaskMapper.to_output(
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
                relations=relations,
            ),
            notes=notes,
        )

    @staticmethod
    def _repeat_by(
        task: Task,
        recurrence: RecurrenceInputDTO,
        request: UpdateTaskInputDTO,
        prefs: UserPrefs,
        now: datetime,
        is_business_day: Callable[[date], bool],
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
            is_business_day=is_business_day,
        )
        if task.due_date is None:
            first: datetime | None = rule.get_next_occurrence()
            if first is not None:
                task.update_due_date(now, first, is_floating=is_floating, tz_name=tz)
        task.change_recurrence(now, rule)


async def _relations_text(
    uow: UnitOfWork, task: Task, user_id: UserId
) -> dict[str, str | None]:
    """The parent and the dependencies as text, for the history."""
    parent: Task | None = (
        await uow.tasks.get_by_id(task.parent_id, user_id) if task.parent_id else None
    )
    waits_on: list[str] = [
        str(found.title)
        for ref in sorted(task.depends_on, key=str)
        if (found := await uow.tasks.get_by_id(ref, user_id)) is not None
    ]
    return {
        "parent": str(parent.title) if parent else None,
        "depends on": ", ".join(waits_on) or None,
    }


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
        "strict": "yes" if task.strict_due else None,
        "tags": " ".join(f"#{t}" for t in sorted(task.tags)) or None,
    }
