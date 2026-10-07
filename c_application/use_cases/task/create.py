from dataclasses import replace
from datetime import date, datetime, time
from typing import Any

from a_core import UniqueId
from a_core.exceptions import ValidationException
from b_domain.entities import Context, Task, User
from b_domain.ports.unit_of_work import UnitOfWork
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import (
    ContextId,
    Description,
    RecurrenceRule,
    TaskId,
    Title,
    UserId,
)
from b_domain.value_objects.enums import EnergyLevel, Priority
from b_domain.value_objects.texts import normalize_tags
from b_domain.value_objects.work_calendar import WorkCalendar, weekdays_only
from c_application.dtos.task_dtos import CreateTaskInputDTO, TaskOutputDTO
from c_application.mappers.task_mapper import TaskMapper
from c_application.use_cases.task.relations import (
    check_takes_subtasks,
    cover_subtasks,
    fit_under,
    relations_of,
    waits_on_open,
)
from c_application.utils import find_context
from c_application.utils.date_input import (
    at_time,
    end_of_day,
    local_today,
    resolve_date_input,
    resolve_horizon,
)
from c_application.utils.recurrence_input import WEEK_STARTS, build_recurrence
from c_application.utils.task_utils import find_task
from c_application.utils.work_calendar import load_work_calendar


# TODO: better system of id prefix when needed, because
#  passing UUID strings are too costly to user
class CreateTaskUseCase(UseCase[CreateTaskInputDTO, TaskOutputDTO]):
    """Use case for orchestrating the creation of a new Task.

    This use case handles:
        1. Identity resolution (User, Parent, Context, Project).
        2. Smart inheritance from User Preferences (Timezone, Active Context).
        3. Complex recurrence rule generation via RecurrenceFactory.
        4. Transactional persistence.
    """

    async def execute(self, dto: CreateTaskInputDTO) -> TaskOutputDTO:
        """Execute the task creation workflow.

        Steps:
            1. Validate and convert input data into value objects.
            2. Resolve user identity and preferences.
            3. Resolve the parent and dependencies (IDs or ID prefixes).
            4. Resolve context associations.
            5. Inherit timezone and priority defaults.
            6. Configure recurrence rules if provided.
            7. Instantiate and persist the Task entity.
            8. Map the entity to an output DTO.

        Args:
            dto (CreateTaskInputDTO): Input data for creating a task.

        Returns:
            TaskOutputDTO: Output DTO representing the newly created task.

        Raises:
            ValidationException: If input data is invalid or domain
                invariants are violated.
            EntityNotFound: If the requested context, parent or dependency
                does not exist (among the user's own).
            AmbiguousIdentifierError: If an ID prefix (context, parent,
                dependency) matches several.
        """

        # 1. Data validation, before touching the data
        try:
            user_id_vo: UserId = UserId.from_string(
                dto.user_id, error_msg="Invalid user ID."
            )
            Title(dto.title)
            normalize_tags(dto.tags)
            Description(dto.description if dto.description else None)
            EnergyLevel.parse(dto.required_energy_level)

        except ValidationException as e:
            raise ValidationException(e) from e

        now_system: datetime = self.clock.now()

        async with self.uow as uow:
            # 2. User resolution & preference fetching
            user: User | None = await uow.users.get_by_id(user_id_vo)
            if not user:
                raise ValidationException(f"User with ID {dto.user_id} not found.")

            task, context = await make_task(uow, dto, user, now_system)
            # Under a parent: its estimate covers its subtasks', and one
            # undo takes both back
            notes: list[str] = []
            if task.parent_id is not None:
                parent: Task | None = await uow.tasks.get_by_id(
                    task.parent_id, user_id_vo
                )
                assert parent is not None
                note: str | None = await cover_subtasks(
                    uow,
                    now_system,
                    parent,
                    [task],
                    caused_by=task.peek_events()[-1].id,
                )
                notes += [note] if note else []
            relations: dict[str, Any] = await relations_of(uow, task, user_id_vo)

        # 9. Return mapped output DTO (recurring: the occurrences ahead)
        today: date = local_today(now_system, user.preferences.timezone)
        horizon: date = resolve_horizon(user.preferences.days_ahead, today=today)
        return replace(
            TaskMapper.to_output(
                task,
                now_system,
                occurrences_until=end_of_day(horizon, user.preferences.timezone),
                context=context,
                relations=relations,
            ),
            notes=notes,
        )


async def make_task(
    uow: UnitOfWork,
    dto: CreateTaskInputDTO,
    user: User,
    now: datetime,
    caused_by: UniqueId | None = None,
) -> tuple[Task, Context | None]:
    """Make the task ``dto`` asks for and add it (the parent's estimate is
    the caller's: once per command).

    A subtask (``dto.parent_id``) takes from its parent what it is not
    given — due date, priority, context — and is refused beyond it (due
    later, priority higher) or repeating.

    Args:
        uow (UnitOfWork): The open unit of work.
        dto (CreateTaskInputDTO): What to make (already validated fields).
        user (User): Whose.
        now (datetime): When.
        caused_by (UniqueId | None): The change that made it along (the
            first of several subtasks added at once).

    Returns:
        tuple[Task, Context | None]: The task and its context.
    """
    user_id_vo: UserId = user.id
    title_vo: Title = Title(dto.title)
    tags: frozenset[str] = normalize_tags(dto.tags)
    description_vo: Description = Description(
        dto.description if dto.description else None
    )
    energy_level_enum = EnergyLevel.parse(dto.required_energy_level)

    # 3. Parent and dependencies: IDs or ID prefixes, among the user's own
    # tasks (as every other command takes them)
    parent: Task | None = (
        await find_task(uow, dto.parent_id, user_id_vo) if dto.parent_id else None
    )
    if parent is not None:
        check_takes_subtasks(parent)
        if dto.recurrence is not None:
            raise ValidationException(
                "A subtask does not repeat: its parent does, and brings it along."
            )
    # A dependency stays within a family: a subtask's only on its siblings
    depends_on_vo: set[TaskId] = set()
    for ref in dto.depends_on:
        blocker: Task = await find_task(uow, ref, user_id_vo)
        if blocker.parent_id != (parent.id if parent is not None else None):
            raise ValidationException(
                f"'{blocker.title}' is a subtask: only its siblings can wait on it."
                if blocker.parent_id is not None
                else "A subtask can only wait on its siblings (its parent can "
                "wait on other tasks)."
            )
        depends_on_vo.add(blocker.id)

    # 4. Smart context resolution: the requested one (name or ID prefix),
    # else the parent's (a subtask), else the active one if it still exists
    context: Context | None = None
    if dto.context_id:
        context = find_context(
            await uow.contexts.list_by_user(user_id_vo), dto.context_id
        )
    elif parent is not None:
        context = (
            await uow.contexts.get_by_id(parent.context_id, user_id_vo)
            if parent.context_id
            else None
        )
    elif dto.use_active_context and user.preferences.active_context_id:
        context = await uow.contexts.get_by_id(
            user.preferences.active_context_id, user_id_vo
        )
    context_id_vo: ContextId | None = context.id if context else None

    # 5. Timezone & priority inheritance (a subtask: its parent's)
    tz_to_use: str = dto.timezone or user.preferences.timezone

    priority: Priority = (
        Priority.parse(dto.priority)
        if dto.priority is not None
        else parent.priority
        if parent is not None
        else Priority.parse(user.preferences.default_task_priority)
    )

    # 6. Dates as typed ("tomorrow", a date alone…), in the user's today; a
    # date without time gets the default due time
    today: date = local_today(now, tz_to_use)
    due_clock: time = user.preferences.default_due_clock
    due_date: datetime | None = (
        at_time(resolve_date_input(dto.due_date, today=today), due_clock)
        if dto.due_date is not None
        else None
    )

    # 7. Configure recurrence
    recurrence_vo: RecurrenceRule | None = None

    if dto.recurrence:
        start: datetime = at_time(
            resolve_date_input(dto.recurrence.start_date, today=today)
            if dto.recurrence.start_date is not None
            else due_date or today,
            due_clock,
        )
        # "The Nth business day": the user's own business days
        calendar: WorkCalendar | None = (
            await load_work_calendar(uow, user_id_vo, user.preferences)
            if dto.recurrence.nth_business_day is not None
            else None
        )
        recurrence_vo = build_recurrence(
            dto.recurrence,
            start=start,
            is_floating=dto.is_floating,
            tz=tz_to_use,
            today=today,
            week_start=WEEK_STARTS[user.preferences.week_start],
            is_business_day=(calendar.is_business_day if calendar else weekdays_only),
        )

        # First occurrence becomes the due date
        # TODO: must add catch_up param
        due_date = recurrence_vo.get_next_occurrence()

    # A subtask with no date of its own is due with its parent
    is_floating: bool = dto.is_floating
    if parent is not None and due_date is None and parent.due_date is not None:
        due_date = parent.due_date.value
        is_floating = parent.due_date.is_floating
        tz_to_use = parent.due_date.timezone or tz_to_use

    # 8. Instantiate and persist domain entity
    task: Task = Task.create(
        now=now,
        user_id=user_id_vo,
        title=title_vo,
        description=description_vo,
        priority=priority,
        parent_id=parent.id if parent else None,
        depends_on=depends_on_vo,
        # It waits only while one of them is open (a done one stays)
        waiting=await waits_on_open(uow, depends_on_vo, user_id_vo),
        context_id=context_id_vo,
        recurrence=recurrence_vo,
        due_date=due_date,
        is_floating=is_floating,
        tz_name=tz_to_use,
        required_energy_level=energy_level_enum,
        estimated_duration_minutes=(
            dto.estimated_minutes or user.preferences.default_task_duration_minutes
        ),
        strict_due=dto.strict_due,
        tags=tags,
        caused_by=caused_by,
    )
    if parent is not None:
        fit_under(
            now,
            task,
            parent,
            due_asked=dto.due_date is not None,
            priority_asked=dto.priority is not None,
        )

    await uow.tasks.add(task)
    return task, context
