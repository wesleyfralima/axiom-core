from uuid import UUID

from a_core.exceptions import ValidationException
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import UserId
from c_application.dtos import TaskOutputDTO
from c_application.dtos.task_dtos import GetTaskRequest
from c_application.mappers.task_mapper import TaskMapper


class GetTaskUseCase(UseCase[None, TaskOutputDTO]):
    """Use case for retrieving the details of a specific task.

    Supports partial ID matching and centralizes mapping via TaskMapper.
    """

    async def execute(self, request: GetTaskRequest) -> TaskOutputDTO:
        """Execute the task retrieval logic.

        Args:
            request (GetTaskRequest): Request object.
        """

        task_id_prefix: str = request.task_id_prefix
        n_occurrences: int = request.n_occurrences

        # 1. Validação de UX (Prefix Matching)
        if len(task_id_prefix) < 4:
            raise ValidationException("O prefixo do ID deve ter pelo menos 4 caracteres.")

        try:
            user_id: UserId =  UserId(UUID(request.user_id))
        except (ValueError, TypeError):
            raise ValidationException("O user_id informado está inválido.")


        async with self.uow:
            # 2. Busca com suporte a prefixo e segurança por user_id
            tasks_found = await self.uow.tasks.find_by_id_prefix(
                id_prefix=task_id_prefix,
                user_id=user_id
            )

            if not tasks_found:
                raise ValidationException(f"Nenhuma tarefa encontrada com o ID '{task_id_prefix}'.")

            if len(tasks_found) > 1:
                conflicting_ids = ", ".join([str(t.id)[:8] for t in tasks_found])
                raise ValidationException(
                    f"ID ambíguo. Encontradas {len(tasks_found)} tarefas: [{conflicting_ids}]. "
                    "Por favor, forneça um prefixo mais específico."
                )

            task = tasks_found[0]

            # 3. Mapeamento centralizado
            # O TaskMapper já lida com status, prioridade e a lista de próximas ocorrências
            return TaskMapper.to_output(task, self.clock.now(), n_occurrences)
