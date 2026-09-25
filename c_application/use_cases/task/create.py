from datetime import datetime

from a_core.exceptions import ValidationException
from b_domain.entities import Task, User
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import (
    ContextId,
    Description,
    RecurrenceRule,
    TaskId,
    Title,
    UserId,
)
from b_domain.value_objects.dates import build_axiom_date
from b_domain.value_objects.enums import EnergyLevel, Priority
from b_domain.value_objects.recurrences import RecurrenceFactory
from c_application.dtos.task_dtos import CreateTaskInputDTO, TaskOutputDTO
from c_application.mappers.task_mapper import TaskMapper


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
            3. Handle parent task validation.
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
        """

        # 1. Data validation
        try:
            user_id_vo: UserId = UserId.from_string(
                dto.user_id, error_msg="Invalid user ID."
            )
            title_vo: Title = Title(dto.title)
            description_vo: Description = Description(
                dto.description if dto.description else None
            )

            energy_level_enum = EnergyLevel.parse(dto.required_energy_level)

        except ValidationException as e:
            raise ValidationException(e)

        try:
            depends_on_vo: set[TaskId] = set(
                [TaskId.from_string(tid) for tid in dto.depends_on]
            )
        except ValidationException as e:
            raise ValidationException(
                "'depends_on' parameter contains invalid UUIDs"
            ) from e

        now_system: datetime = self.clock.now()

        async with self.uow as uow:
            # 2. User resolution & preference fetching
            user: User | None = await uow.users.get_by_id(user_id_vo)
            if not user:
                raise ValidationException(f"User with ID {dto.user_id} not found.")

            # 3. Parent task resolution
            parent_id_vo: TaskId | None = None
            if dto.parent_id:
                try:
                    parent_id: TaskId = TaskId.from_string(
                        dto.parent_id, error_msg="Invalid parent ID."
                    )
                    parent: Task | None = await uow.tasks.get_by_id(parent_id)
                    if not parent or parent.user_id != user_id_vo:
                        raise ValidationException("Parent task not found.")
                    parent_id_vo = parent.id
                except (ValueError, TypeError):
                    raise ValidationException("Invalid parent task ID format.")

            # 4. Smart context resolution
            context_id_vo: ContextId | None = None
            if dto.context_id:
                context_id_vo = ContextId.from_string(
                    dto.context_id, error_msg="Invalid context ID."
                )
            elif user.preferences.active_context_id:
                context_id_vo = user.preferences.active_context_id

            # 5. Timezone & priority inheritance
            tz_to_use: str = dto.timezone or user.preferences.timezone

            priority: Priority = Priority.parse(
                dto.priority or user.preferences.default_task_priority
            )

            # 6. Configure recurrence
            recurrence_vo: RecurrenceRule | None = None
            due_date: datetime | None = dto.due_date

            if dto.recurrence:
                start_axiom = build_axiom_date(
                    dto.recurrence.start_date or dto.due_date or now_system,
                    is_floating=dto.is_floating,
                    tz=tz_to_use,
                )
                end_axiom = None
                if dto.recurrence.end_date:
                    end_axiom = build_axiom_date(
                        dto.recurrence.end_date,
                        is_floating=dto.is_floating,
                        tz=tz_to_use,
                    )

                recurrence_vo = RecurrenceFactory.create_from_input(
                    start_date=start_axiom,
                    end_date=end_axiom,
                    frequency=dto.recurrence.frequency,
                    interval=dto.recurrence.interval,
                    count=dto.recurrence.count,
                    days_of_week=(
                        set(dto.recurrence.by_week_days)
                        if dto.recurrence.by_week_days
                        else None
                    ),
                    days_of_month=(
                        set(dto.recurrence.by_month_days)
                        if dto.recurrence.by_month_days
                        else None
                    ),
                    set_pos=dto.recurrence.by_set_pos,
                    nth_business_day=dto.recurrence.nth_business_day,
                    is_business_day_checker=lambda dt: (
                        dt.weekday() < 5
                    ),  # Simple weekday check  TODO: change this
                )

                # First occurrence becomes the due date
                # TODO: must add catch_up param
                due_date = recurrence_vo.get_next_occurrence()

            # 7. Instantiate and persist domain entity
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
            )

            await uow.tasks.add(task)

        # 8. Return mapped output DTO
        return TaskMapper.to_output(task, now_system)
