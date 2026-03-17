from dataclasses import replace
from uuid import uuid4

import pytest

from a_core import ValidationException, InvalidStateTransition
from b_domain.entities import Task, User
from b_domain.value_objects import TaskStatus, TaskId, Title
from c_application.dtos.task_dtos import TaskByUserRequest
from c_application.use_cases import CompleteTaskUseCase


@pytest.mark.asyncio
@pytest.mark.uc
async def test_complete_task_successfully(create_use_case_context, fake_uow):
    clock = create_use_case_context["clock"]

    # 1. Setup do estado inicial
    # IMPORTANTE: Usar os objetos de ID tipados, não strings
    user = User.create(username="wesley")

    # Passamos o user.id (UserId) diretamente
    task = Task.create(
        title=Title("Test Task"),
        user_id=user.id,
        now=clock.now(),
    )

    # Populamos o Fake UOW
    await fake_uow.tasks.add(task)
    await fake_uow.users.add(user)

    # 2. Instanciar Use Case
    use_case = CompleteTaskUseCase(**create_use_case_context)

    # No DTO, o user_id costuma vir como string da API/CLI, 
    # o Use Case se encarrega de converter ou validar se necessário.
    request = TaskByUserRequest(
        task_id_prefix=str(task.id)[:8],
        user_id=str(user.id),
        completed_at=clock.now(),
    )

    # 3. Execução
    result = await use_case.execute(request)

    # 4. Asserções
    # Verificamos o status através do Enum/ValueObject
    assert result.completed_task.status == TaskStatus.DONE

    # Verificamos se a tarefa no repositório foi realmente atualizada
    updated_task = await fake_uow.tasks.get_by_id(task.id)
    assert updated_task.status == TaskStatus.DONE

    # Verificamos a atomicidade
    assert fake_uow.committed is True
    assert fake_uow.rolled_back is False


# -------------------------------------------------------------------------
# 1. Erro: Prefixo muito curto
# -------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.uc
async def test_complete_task_fails_if_prefix_too_short(create_use_case_context):
    use_case = CompleteTaskUseCase(**create_use_case_context)
    request = TaskByUserRequest(task_id_prefix="abc", user_id=str(uuid4()))

    with pytest.raises(ValidationException, match="The ID prefix must be at least 4 characters long"):
        await use_case.execute(request)


# -------------------------------------------------------------------------
# 2. Erro: ID Ambíguo (Múltiplas tarefas com mesmo prefixo)
# -------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.uc
async def test_complete_task_fails_if_prefix_is_ambiguous(create_use_case_context, fake_uow):
    user = User.create(username="wesley")
    clock = create_use_case_context["clock"]
    now = clock.now()

    # Criamos duas tarefas que começam com o mesmo TaskId
    # Forçamos o ID para o teste ser determinístico
    tid = TaskId()
    t1 = Task.create(title=Title("Task 1"), user_id=user.id, now=now)
    t1 = replace(t1, id=tid)
    t2 = Task.create(title=Title("Task 2"), user_id=user.id, now=now)
    t2 = replace(t2, id=tid)

    # Simulamos o cenário no fake repositório
    await fake_uow.tasks.add(t1)
    await fake_uow.tasks.add(t2)

    use_case = CompleteTaskUseCase(**create_use_case_context)
    # Usamos um prefixo que (teoricamente) bateria em ambas se tivessem IDs similares
    # No fake, o find_by_id_prefix deve ser populado para retornar ambas

    request = TaskByUserRequest(task_id_prefix=str(t1.id)[:4], user_id=str(user.id))

    # Se o repositório fake retornar mais de uma, o UC deve barrar
    with pytest.raises(ValidationException, match="Ambiguous ID"):
        await use_case.execute(request)


# -------------------------------------------------------------------------
# 3. Regra de Negócio: Bloqueio por Dependências
# -------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.uc
async def test_complete_task_fails_if_task_is_blocked(create_use_case_context, fake_uow):
    user = User.create(username="wesley")
    clock = create_use_case_context["clock"]
    now = clock.now()

    task_a = Task.create(title=Title("Task A"), user_id=user.id, now=now)
    task_b = Task.create(title=Title("Task B"), user_id=user.id, now=now)

    task_b.add_dependency(task_a.id)  # B depende de A

    await fake_uow.tasks.add(task_a)
    await fake_uow.tasks.add(task_b)
    await fake_uow.users.add(user)

    use_case = CompleteTaskUseCase(**create_use_case_context)

    # Tentar completar B sem completar A antes
    request = TaskByUserRequest(task_id_prefix=str(task_b.id)[:8], user_id=str(user.id))

    with pytest.raises(InvalidStateTransition, match="Task is blocked by dependencies"):
        await use_case.execute(request)


# -------------------------------------------------------------------------
# 4. Fluxo Social: Parar Timers Ativos e Desbloquear Próxima
# -------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.uc
async def test_complete_task_fails_if_belongs_to_another_user(create_use_case_context, fake_uow):
    clock = create_use_case_context["clock"]
    now = clock.now()

    # Setup: Tarefa pertence ao 'outro'
    wesley = User.create(username="wesley")
    outro = User.create(username="outro")
    task_do_outro = Task.create(title=Title("Tarefa Secreta"), user_id=outro.id, now=now)

    await fake_uow.tasks.add(task_do_outro)
    await fake_uow.users.add(wesley)

    use_case = CompleteTaskUseCase(**create_use_case_context)

    # Wesley tenta completar usando o prefixo da tarefa do outro
    request = TaskByUserRequest(
        task_id_prefix=str(task_do_outro.id)[:8],
        user_id=str(wesley.id)
    )

    with pytest.raises(ValidationException, match="No task found with ID prefix"):
        await use_case.execute(request)


@pytest.mark.asyncio
@pytest.mark.uc
async def test_complete_task_fails_if_already_done(create_use_case_context, fake_uow):
    clock = create_use_case_context["clock"]
    now = clock.now()

    user = User.create(username="wesley")
    task = Task.create(title=Title("Já fiz"), user_id=user.id, now=now)
    task.mark_as_done(create_use_case_context["clock"].now())  # Forçamos o estado DONE

    await fake_uow.tasks.add(task)
    await fake_uow.users.add(user)

    use_case = CompleteTaskUseCase(**create_use_case_context)
    request = TaskByUserRequest(task_id_prefix=str(task.id)[:8], user_id=str(user.id))

    with pytest.raises(InvalidStateTransition, match="Task is already completed."):
        await use_case.execute(request)
