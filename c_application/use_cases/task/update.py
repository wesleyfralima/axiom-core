from typing import List
from uuid import UUID

from a_core.exceptions import ValidationException
from b_domain.entities import Task
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import UserId
from c_application.dtos.task_dtos import UpdateTaskInputDTO, TaskOutputDTO
from c_application.mappers.task_mapper import TaskMapper


class UpdateTaskUseCase(UseCase[UpdateTaskInputDTO, TaskOutputDTO]):
    """Asynchronous use case for partial task updates.

    Supports partial ID matching and ensures domain rules are respected
    during the update process.
    """

    async def execute(self, request: UpdateTaskInputDTO) -> "TaskOutputDTO":
        """Execute the task update logic.

        Args:
            request (UpdateTaskRequest): Input data for partial task updates.
        """

        now = self.clock.now()

        # 1. Validação de Prefixo (UX consistente com Delete/Complete/Get)
        if len(request.task_id_prefix) < 4:
            raise ValidationException("O prefixo do ID deve ter pelo menos 4 caracteres.")

        try:
            user_id: UserId = UserId(UUID(request.user_id))
        except (ValueError, TypeError):
            raise ValidationException("O userId informado não é válido.")

        async with self.uow:
            # 2. Busca por prefixo com filtro de usuário
            tasks_found: List["Task"] = await self.uow.tasks.find_by_id_prefix(
                id_prefix=request.task_id_prefix,
                user_id=user_id
            )

            if not tasks_found:
                raise ValidationException(f"Tarefa com ID '{request.task_id_prefix}' não encontrada.")

            if len(tasks_found) > 1:
                conflicting_ids = ", ".join([str(t.id)[:8] for t in tasks_found])
                raise ValidationException(
                    f"ID ambíguo. Encontradas {len(tasks_found)} tarefas: [{conflicting_ids}]."
                )

            task = tasks_found[0]

            # 3. Aplicação de Mudanças Parciais
            # Delegamos para a entidade validar as regras de negócio de cada campo
            if request.title is not None:
                task.rename(now, request.title)

            if request.description is not None:
                task.update_description(now, request.description)

            if request.priority is not None:
                task.update_priority(now, request.priority)

            if request.due_date is not None:
                # Aqui você pode adicionar lógica de timezone se necessário
                task.update_due_date(now, request.due_date)

            # 4. Persistência
            await self.uow.tasks.update(task)

        # 5. Retorno via Mapper
        return TaskMapper.to_output(task, now)
