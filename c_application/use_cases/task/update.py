from datetime import date, datetime

from a_core import IdPrefix
from a_core.exceptions import ValidationException
from b_domain.entities import Context, Task, User
from b_domain.entities.user import UserPrefs
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import Priority, UserId
from b_domain.value_objects.enums import EnergyLevel
from c_application.dtos.task_dtos import TaskOutputDTO, UpdateTaskInputDTO
from c_application.mappers.task_mapper import TaskMapper
from c_application.utils import find_context
from c_application.utils.date_input import (
    at_time,
    end_of_day,
    local_today,
    resolve_date_input,
    resolve_horizon,
)


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

            # 4. Persistence
            await uow.tasks.update(task)

            context = (
                await uow.contexts.get_by_id(task.context_id, user_id)
                if task.context_id
                else None
            )

        # 5. Return mapped output DTO (recurring: the occurrences ahead)
        horizon: date = resolve_horizon(
            prefs.days_ahead, today=local_today(now, prefs.timezone)
        )
        return TaskMapper.to_output(
            task,
            now,
            occurrences_until=end_of_day(horizon, prefs.timezone),
            context=context,
        )
