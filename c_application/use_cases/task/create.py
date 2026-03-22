from datetime import timezone, datetime
from typing import Optional
from uuid import UUID

from a_core.exceptions import ValidationException
from b_domain.entities import Task, User
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import TaskId, UserId, ContextId, Title, Description, RecurrenceRule
from b_domain.value_objects.enums import EnergyLevel, Priority
from b_domain.value_objects.recurrences import RecurrenceFactory
from c_application.dtos.task_dtos import CreateTaskInputDTO, TaskOutputDTO
from c_application.mappers.task_mapper import TaskMapper


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
            ValidationException: If input data is invalid or domain invariants are violated.
        """

        # 1. Data validation
        try:
            user_id_vo: UserId = UserId.from_string(dto.user_id)
            title_vo: Title = Title(dto.title)
            description_vo: Description = Description(dto.description if dto.description else None)

            energy_level_enum: EnergyLevel | None = None
            if dto.required_energy_level:
                energy_level_enum = EnergyLevel(dto.required_energy_level)

        except (ValueError, TypeError):
            raise ValidationException("Invalid user ID format.")

        except ValidationException as e:
            raise ValidationException(str(e))

        try:
            depends_on_vo: set[TaskId] = set([TaskId.from_string(tid) for tid in dto.depends_on])
        except (ValueError, TypeError) as e:
            raise ValidationException("'depends_on' parameter contains invalid UUIDs") from e

        now_system: datetime = self.clock.now()

        async with self.uow as uow:

            # 2. User resolution & preference fetching
            user: User = await uow.users.get_by_id(user_id_vo)
            if not user:
                raise ValidationException(f"User with ID {dto.user_id} not found.")

            # 3. Parent task resolution
            parent_id_vo: Optional[TaskId] = None
            if dto.parent_id:
                try:
                    parent: Task | None = await uow.tasks.get_by_id(TaskId(UUID(dto.parent_id)))
                    if not parent or parent.user_id != user_id_vo:
                        raise ValidationException("Parent task not found or access denied.")
                    parent_id_vo = parent.id
                except (ValueError, TypeError):
                    raise ValidationException("Invalid parent task ID format.")

            # 4. Smart context resolution
            context_id_vo: ContextId | None = None
            if dto.context_id:
                context_id_vo = ContextId(UUID(dto.context_id))
            elif user.preferences.active_context_id:
                context_id_vo = user.preferences.active_context_id

            # 5. Timezone & priority inheritance
            tz_to_use: str = dto.timezone or user.preferences.timezone
            priority_to_use: str = dto.priority or user.preferences.default_task_priority

            try:
                priority: Priority = Priority(priority_to_use)
            except (ValueError, TypeError):
                raise ValidationException("Invalid priority.")

            # 6. Configure recurrence
            recurrence_vo: RecurrenceRule | None = None
            due_date: datetime | None = dto.due_date

            if dto.recurrence:
                start_base: datetime = dto.recurrence.start_date or dto.due_date or now_system
                end_date_clean: datetime | None = dto.recurrence.end_date

                # Handle timezone awareness
                if dto.is_floating:
                    start_base = start_base.replace(tzinfo=None)
                    if end_date_clean:
                        end_date_clean = end_date_clean.replace(tzinfo=None)
                else:
                    if start_base.tzinfo is None:
                        start_base = start_base.replace(tzinfo=timezone.utc)
                    if end_date_clean and end_date_clean.tzinfo is None:
                        end_date_clean = end_date_clean.replace(tzinfo=timezone.utc)

                recurrence_vo = RecurrenceFactory.create_from_input(
                    start_date=start_base,
                    end_date=end_date_clean,
                    frequency=dto.recurrence.frequency,
                    interval=dto.recurrence.interval,
                    count=dto.recurrence.count,
                    days_of_week=set(dto.recurrence.by_week_days) if dto.recurrence.by_week_days else None,
                    days_of_month=set(dto.recurrence.by_month_days) if dto.recurrence.by_month_days else None,
                    set_pos=dto.recurrence.by_set_pos,
                    nth_business_day=dto.recurrence.nth_business_day,
                    is_business_day_checker=lambda dt: dt.weekday() < 5,  # Simple weekday check
                )

                # First occurrence becomes the due date
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
