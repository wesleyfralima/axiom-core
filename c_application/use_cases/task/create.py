from datetime import date, datetime, time

from a_core.exceptions import ValidationException
from b_domain.entities import Context, Task, User
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

        # 1. Data validation
        try:
            user_id_vo: UserId = UserId.from_string(
                dto.user_id, error_msg="Invalid user ID."
            )
            title_vo: Title = Title(dto.title)
            tags: frozenset[str] = normalize_tags(dto.tags)
            description_vo: Description = Description(
                dto.description if dto.description else None
            )

            energy_level_enum = EnergyLevel.parse(dto.required_energy_level)

        except ValidationException as e:
            raise ValidationException(e) from e

        now_system: datetime = self.clock.now()

        async with self.uow as uow:
            # 2. User resolution & preference fetching
            user: User | None = await uow.users.get_by_id(user_id_vo)
            if not user:
                raise ValidationException(f"User with ID {dto.user_id} not found.")

            # 3. Parent and dependencies: IDs or ID prefixes, among the
            # user's own tasks (as every other command takes them)
            parent_id_vo: TaskId | None = (
                (await find_task(uow, dto.parent_id, user_id_vo)).id
                if dto.parent_id
                else None
            )
            depends_on_vo: set[TaskId] = {
                (await find_task(uow, ref, user_id_vo)).id for ref in dto.depends_on
            }

            # 4. Smart context resolution: the requested one (name or ID
            # prefix), else the active one if it still exists
            context: Context | None = None
            if dto.context_id:
                context = find_context(
                    await uow.contexts.list_by_user(user_id_vo), dto.context_id
                )
            elif dto.use_active_context and user.preferences.active_context_id:
                context = await uow.contexts.get_by_id(
                    user.preferences.active_context_id, user_id_vo
                )
            context_id_vo: ContextId | None = context.id if context else None

            # 5. Timezone & priority inheritance
            tz_to_use: str = dto.timezone or user.preferences.timezone

            priority: Priority = Priority.parse(
                dto.priority or user.preferences.default_task_priority
            )

            # 6. Dates as typed ("tomorrow", a date alone…), in the user's
            # today; a date without time gets the default due time
            today: date = local_today(now_system, tz_to_use)
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
                    is_business_day=(
                        calendar.is_business_day if calendar else weekdays_only
                    ),
                )

                # First occurrence becomes the due date
                # TODO: must add catch_up param
                due_date = recurrence_vo.get_next_occurrence()

            # 8. Instantiate and persist domain entity
            task: Task = Task.create(
                now=now_system,
                user_id=user_id_vo,
                title=title_vo,
                description=description_vo,
                priority=priority,
                parent_id=parent_id_vo,
                depends_on=depends_on_vo,
                context_id=context_id_vo,
                recurrence=recurrence_vo,
                due_date=due_date,
                is_floating=dto.is_floating,
                tz_name=tz_to_use,
                required_energy_level=energy_level_enum,
                estimated_duration_minutes=(
                    dto.estimated_minutes
                    or user.preferences.default_task_duration_minutes
                ),
                tags=tags,
            )

            await uow.tasks.add(task)

        # 9. Return mapped output DTO (recurring: the occurrences ahead)
        horizon: date = resolve_horizon(user.preferences.days_ahead, today=today)
        return TaskMapper.to_output(
            task,
            now_system,
            occurrences_until=end_of_day(horizon, user.preferences.timezone),
            context=context,
        )
