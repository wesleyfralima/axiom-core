from typing import List, Optional, TYPE_CHECKING
from uuid import UUID

from a_core.exceptions import EntityNotFound, ValidationException
from b_domain.ports.repositories import TaskFilter
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import TaskId, TaskStatus, Priority, UserId
from c_application.dtos.task_dtos import TaskOutputDTO, ListTasksRequest
from c_application.mappers.task_mapper import TaskMapper

if TYPE_CHECKING:
    from b_domain.entities import Task


class ListTasksUseCase(UseCase[ListTasksRequest, List[TaskOutputDTO]]):
    """Use case for listing tasks with filtering and domain mapping."""

    async def execute(self, request: ListTasksRequest) -> List[TaskOutputDTO]:
        """Execute the task listing logic."""

        async with self.uow:
            # 1. Validação e Resolução de Value Objects
            try:
                f_status = TaskStatus(request.status) if request.status else None
            except ValueError:
                raise EntityNotFound(entity_name="TaskStatus", identifier=request.status)

            try:
                f_priority = Priority(request.priority) if request.priority else None
            except ValueError:
                raise EntityNotFound(entity_name="Priority", identifier=request.priority)

            try:
                f_user_id: UserId = UserId(UUID(request.user_id))
            except (ValueError, TypeError):
                raise ValidationException("O user_id informado está inválido.")

            f_parent_id: Optional[TaskId] = None
            if request.parent_id:
                try:
                    f_parent_id = TaskId(UUID(request.parent_id))
                except (ValueError, TypeError):
                    # Se o ID do pai for inválido, retornamos vazio (comportamento seguro)
                    return []

            # 2. Montagem do Filtro de Domínio
            filters = TaskFilter(
                user_id=f_user_id,
                status=f_status,
                priority=f_priority,
                parent_id=f_parent_id,
                tags=request.tags,
                only_roots=request.only_roots,
            )

            # 3. Consulta ao Repositório
            tasks: List["Task"] = await self.uow.tasks.list(filters)

            # 4. Mapeamento via TaskMapper
            # Passamos o clock.now() uma vez para ser reaproveitado no loop
            now = self.clock.now()
            return [TaskMapper.to_output(task, now) for task in tasks]
