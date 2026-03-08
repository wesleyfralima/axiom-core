from typing import TYPE_CHECKING, List
from uuid import UUID

from a_core.exceptions import ValidationException
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import UserId
from c_application.dtos.task_dtos import TaskByUserRequest

if TYPE_CHECKING:
    from b_domain.entities import Task


class DeleteTaskUseCase(UseCase[TaskByUserRequest, None]):
    """Use case for deleting a Task with partial ID support.

    Ensures that tasks are deleted safely within a transactional context,
    validating ownership and preventing ambiguous prefix deletions.
    """

    async def execute(self, request: TaskByUserRequest) -> None:
        """Execute the task deletion logic.

        Args:
            request (TaskByUserRequest): Request object with task_id_prefix and user_id.
        """

        task_id_prefix: str = request.task_id_prefix

        # 1. Fail Fast: Segurança mínima de UX
        if len(task_id_prefix) < 4:
            raise ValidationException("O prefixo do ID deve ter pelo menos 4 caracteres.")

        try:
            user_id: UserId =  UserId(UUID(request.user_id))
        except (ValueError, TypeError):
            raise ValidationException("O user_id informado está inválido.")

        async with self.uow:
            # 2. Busca por prefixo (reaproveitando a lógica de ambiguidade)
            tasks_found: List["Task"] = await self.uow.tasks.find_by_id_prefix(
                id_prefix=task_id_prefix,
                user_id=user_id,
            )

            if not tasks_found:
                raise ValidationException(f"Nenhuma tarefa encontrada com o ID '{task_id_prefix}'.")

            if len(tasks_found) > 1:
                conflicting_ids = ", ".join([str(t.id)[:8] for t in tasks_found])
                raise ValidationException(
                    f"ID ambíguo. Encontradas {len(tasks_found)} tarefas: [{conflicting_ids}]. "
                    "Seja mais específico para evitar deletar a tarefa errada."
                )

            task_to_delete = tasks_found[0]

            await self.uow.tasks.delete(task_to_delete.id)
