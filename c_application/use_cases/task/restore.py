from dataclasses import dataclass
from datetime import datetime

from a_core import DTO, EntityNotFound, IdPrefix
from a_core.exceptions import AmbiguousIdentifierError
from b_domain.entities import Task
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import UserId
from c_application.dtos import TaskOutputDTO
from c_application.dtos.task_dtos import TaskByUserRequest
from c_application.mappers.task_mapper import TaskMapper


@dataclass(frozen=True, kw_only=True)
class TaskRestoredOutputDTO(DTO):
    """A deleted task, back as it was."""

    task: TaskOutputDTO


class RestoreTaskUseCase(UseCase[TaskByUserRequest, TaskRestoredOutputDTO]):
    """Bring a deleted task back (until it is purged)."""

    async def execute(self, request: TaskByUserRequest) -> TaskRestoredOutputDTO:
        """Restore one of the user's deleted tasks, found by ID prefix.

        Raises:
            ValidationException: If the user ID or the prefix is invalid.
            EntityNotFound: If no deleted task of the user matches (never
                deleted, or already purged).
            AmbiguousIdentifierError: If the prefix matches several.
        """
        prefix: IdPrefix = IdPrefix(request.task_id_prefix)
        user_id: UserId = UserId.from_string(
            request.user_id, error_msg="Invalid user ID."
        )
        now: datetime = self.clock.now()

        async with self.uow as uow:
            found: list[Task] = await uow.tasks.find_by_id_prefix(
                id_prefix=prefix, user_id=user_id, deleted=True
            )
            if not found:
                raise EntityNotFound(entity_name="Deleted task", identifier=str(prefix))
            if len(found) > 1:
                raise AmbiguousIdentifierError(
                    resource_name="deleted tasks",
                    identifier=str(prefix),
                    matches=[str(t.id)[:8] for t in found],
                )
            task: Task = found[0]
            task.restore(now)
            await uow.tasks.update(task)
            context = (
                await uow.contexts.get_by_id(task.context_id, user_id)
                if task.context_id
                else None
            )
            return TaskRestoredOutputDTO(
                task=TaskMapper.to_output(task, now, context=context)
            )
