from datetime import datetime
from typing import TYPE_CHECKING, Optional, List
from uuid import UUID

from a_core.exceptions import ValidationException, InvalidStateTransition
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import TaskStatus, UserId
from c_application.dtos.task_dtos import CompleteTaskOutputDTO, TaskByUserRequest
from c_application.mappers.task_mapper import TaskMapper

if TYPE_CHECKING:
    from b_domain.entities import Task


class CompleteTaskUseCase(UseCase[TaskByUserRequest, CompleteTaskOutputDTO]):
    """Use case for completing a Task with support for partial ID matching.

    Allows users to provide a partial UUID (prefix) to identify a task.
    Ensures that ambiguous matches result in an error to prevent
    unintended task completions.
    """

    async def execute(self, request: TaskByUserRequest) -> CompleteTaskOutputDTO:
        """Execute the task completion logic.

        Args:
            request (TaskByUserRequest): Request object containing task_id_prefix and user_id.

        Returns:
            CompleteTaskOutputDTO: DTO with the completed task and any new occurrence.
        """

        task_id_prefix: str = request.task_id_prefix
        task_next_created: Optional["Task"] = None
        now: datetime = request.completed_at or self.clock.now()

        # 1. Validações
        # 1.1. Validação de Segurança de UX
        if len(task_id_prefix) < 4:
            raise ValidationException("O prefixo do ID deve ter pelo menos 4 caracteres para busca.")

        # 1.2. Validação do user_id informado
        try:
            user_id: UserId = UserId(UUID(request.user_id)) if request.user_id else None
        except ValueError:
            raise ValidationException("O user_id informado é inválido.")

        # 2. Bloco Transacional: Busca e Persistência
        async with self.uow:

            # Busca por prefixo filtrando pelo usuário (Boundary de Segurança)
            tasks_found: List["Task"] = await self.uow.tasks.find_by_id_prefix(
                id_prefix=task_id_prefix,
                user_id=user_id,
            )

            if not tasks_found:
                raise ValidationException(f"Nenhuma tarefa encontrada com o ID '{task_id_prefix}'.")

            if len(tasks_found) > 1:
                # Tratamento de Ambiguidade
                # Mostramos os primeiros 8 caracteres dos IDs conflitantes para ajudar o usuário
                conflicting_ids = ", ".join([str(t.id)[:8] for t in tasks_found])
                raise ValidationException(
                    f"ID ambíguo. Encontradas {len(tasks_found)} tarefas: [{conflicting_ids}]. "
                    "Por favor, forneça um prefixo mais específico."
                )

            # Extraímos a única tarefa encontrada
            task = tasks_found[0]

            # Se já está completa, erro
            if task.status == TaskStatus.DONE:
                raise InvalidStateTransition("task is already DONE")

            # Se bloqueada, erro
            if task.is_blocked:
                raise InvalidStateTransition("complete all blocking tasks first")

            # Encerrar qualquer TimeEntry (Timer) ativo para esta tarefa
            actual_duration_minutes: int = 0
            active_timers = await self.uow.time_entries.get_actives_for_task(task.id)
            if active_timers:
                for t in active_timers:
                    t.stop(request.completed_at)
                    actual_duration_minutes += t.elapsed_minutes(now)
                await self.uow.time_entries.update_all(active_timers)

            task.attempt_count += 1
            task.success_count += 1

            # Recalcula a média de tempo (Média Móvel Simples)
            if actual_duration_minutes > 0:
                if task.success_count == 1:
                    task.average_duration_minutes = actual_duration_minutes
                else:
                    total_past_time: int = task.average_duration_minutes * (task.success_count - 1)  # Subtrai a atual
                    task.average_duration_minutes = (total_past_time + actual_duration_minutes) // task.success_count

            # --- Lógica de Conclusão ---
            task.mark_as_done(now, actual_minutes=actual_duration_minutes)

            # Gerar próxima ocorrência se aplicável
            next_task = task.create_next_occurrence(now)
            if next_task:
                # A nova ocorrência herda a média de tempo aprendida para predições futuras!
                next_task.estimated_duration_minutes = task.average_duration_minutes
                task_next_created = await self.uow.tasks.add(next_task)

            # 3. Desbloqueio de Dependências (Efeito Cascata)
            blocked_tasks = await self.uow.tasks.find_tasks_blocked_by(task.id)
            if blocked_tasks:
                for blocked in blocked_tasks:
                    blocked.remove_dependency(task.id)
                # Se a tarefa agora não tem mais bloqueios, poderíamos até
                # disparar uma notificação ou mudar um status interno
                await self.uow.tasks.update_many(blocked_tasks)

            await self.uow.tasks.update(task)

        return CompleteTaskOutputDTO(
            completed_task=TaskMapper.to_output(task, now),
            next_occurrence=TaskMapper.to_output(task_next_created, now) if task_next_created else None,
        )
