"""Add subtasks to a task — its checklist, as tasks (``axpro task add-to``)."""

from datetime import datetime

from a_core import UniqueId
from a_core.exceptions import ValidationException
from b_domain.entities import Context, Task, User
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import UserId
from c_application.dtos.task_dtos import (
    AddSubtasksInputDTO,
    CreateTaskInputDTO,
    DayLoadDTO,
    SubtasksAddedOutputDTO,
)
from c_application.mappers.task_mapper import TaskMapper
from c_application.use_cases.task.capacity import full_day_of
from c_application.use_cases.task.create import make_task
from c_application.use_cases.task.relations import cover_subtasks, relations_of
from c_application.utils.task_utils import find_task


class AddSubtasksUseCase(UseCase[AddSubtasksInputDTO, SubtasksAddedOutputDTO]):
    """Add one subtask per title under a task, in one change.

    Each subtask takes from its parent what it is not given (due date,
    priority, context) and is refused beyond it. The parent's estimate grows
    to cover them when they take longer together. One undo takes it all
    back: the later subtasks and the estimate are linked to the first one's
    creation.
    """

    async def execute(self, request: AddSubtasksInputDTO) -> SubtasksAddedOutputDTO:
        """Add them.

        Raises:
            ValidationException: If there is no title, the user ID is
                invalid, the parent cannot take subtasks (a subtask itself,
                closed, deleted) or something asked is beyond it.
            EntityNotFound: If the user has no such parent.
            AmbiguousIdentifierError: If the parent's prefix matches several.
        """
        titles: list[str] = [t.strip() for t in request.titles if t.strip()]
        if not titles:
            raise ValidationException("Give at least one subtask title.")
        user_id: UserId = UserId.from_string(
            request.user_id, error_msg="Invalid user ID."
        )
        now: datetime = self.clock.now()

        async with self.uow as uow:
            user: User | None = await uow.users.get_by_id(user_id)
            if user is None:
                raise ValidationException(f"User with ID {request.user_id} not found.")
            parent: Task = await find_task(uow, request.parent_id, user_id)

            made: list[tuple[Task, Context | None]] = []
            first: UniqueId | None = None
            for title in titles:
                task, context = await make_task(
                    uow,
                    CreateTaskInputDTO(
                        user_id=request.user_id,
                        title=title,
                        description=request.description,
                        priority=request.priority,
                        required_energy_level=request.required_energy_level,
                        estimated_minutes=request.estimated_minutes,
                        tags=request.tags,
                        due_date=request.due_date,
                        parent_id=str(parent.id),
                    ),
                    user,
                    now,
                    caused_by=first,
                )
                if first is None:
                    first = task.peek_events()[-1].id
                made.append((task, context))

            note: str | None = await cover_subtasks(
                uow, now, parent, [t for t, _ in made], caused_by=first
            )
            parent_context: Context | None = (
                await uow.contexts.get_by_id(parent.context_id, user_id)
                if parent.context_id
                else None
            )
            parent_out = TaskMapper.to_output(
                parent,
                now,
                context=parent_context,
                relations=await relations_of(uow, parent, user_id),
            )

        # Its estimate may have grown: its day, when full (warned only)
        async with self.uow as uow:
            full_day: DayLoadDTO | None = await full_day_of(uow, user_id, parent, now)

        return SubtasksAddedOutputDTO(
            full_day=full_day,
            parent=parent_out,
            subtasks=[
                TaskMapper.to_output(task, now, context=context)
                for task, context in made
            ],
            notes=[note] if note else [],
        )
