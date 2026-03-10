from dataclasses import replace
from uuid import uuid4

import pytest

from a_core import ValidationException, InvalidStateTransition
from b_domain.entities import Task, User, TimeEntry
from b_domain.value_objects import TaskStatus, TaskId, RecurrenceInterval, Title
from b_domain.value_objects.recurrences.simple import SimpleIntervalRule
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

    with pytest.raises(ValidationException, match="pelo menos 4 caracteres"):
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
    with pytest.raises(ValidationException, match="ID ambíguo"):
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

    with pytest.raises(InvalidStateTransition, match="complete all blocking tasks first"):
        await use_case.execute(request)


# -------------------------------------------------------------------------
# 4. Fluxo Social: Parar Timers Ativos e Desbloquear Próxima
# -------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.uc
async def test_complete_task_stops_timer_and_unlocks_successors(create_use_case_context, fake_uow):
    # 1. Setup
    user = User.create(username="wesley")
    clock = create_use_case_context["clock"]
    now = clock.now()

    # Tarefa A bloqueia B
    task_a = Task.create(title=Title("Tarefa A"), user_id=user.id, now=now)
    task_b = Task.create(title=Title("Tarefa B"), user_id=user.id, now=now)
    task_b.add_dependency(task_a.id)

    # Criamos um TimeEntry ativo (sem end_time) para a Tarefa A
    timer = TimeEntry(
        task_id=task_a.id,
        user_id=user.id,
        start_time=now,
        description="Focando na Tarefa A"
    )

    # Populamos o Fake UOW
    await fake_uow.users.add(user)
    await fake_uow.tasks.add(task_a)
    await fake_uow.tasks.add(task_b)
    await fake_uow.time_entries.add(timer)

    # 2. Execução
    use_case = CompleteTaskUseCase(**create_use_case_context)

    # Simulamos que a conclusão ocorre 30 minutos depois
    # (Opcional: avançar o clock se o FakeClock permitir)
    request = TaskByUserRequest(
        task_id_prefix=str(task_a.id)[:8],
        user_id=str(user.id),
        completed_at=now  # Usando o tempo do clock
    )

    await use_case.execute(request)

    # 3. Asserções de Time Tracking
    # Buscamos a entrada do repositório para garantir que a persistência foi chamada
    entries = await fake_uow.time_entries.find_by_user(user.id)
    updated_timer = entries[0]

    assert updated_timer.end_time is not None, "O timer deveria ter sido encerrado."
    assert updated_timer.end_time == now, "O end_time deve ser o timestamp de conclusão."
    assert updated_timer.elapsed_minutes(now=now) >= 0

    # 4. Asserções de Grafo de Dependências
    updated_b = await fake_uow.tasks.get_by_id(task_b.id)

    assert task_a.id not in updated_b.depends_on, "A dependência de A deveria ter sido removida de B."
    assert updated_b.is_blocked is False, "A tarefa B deveria estar desbloqueada agora."

    # 5. Atomicidade
    assert fake_uow.committed is True


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

    with pytest.raises(ValidationException, match="Nenhuma tarefa encontrada"):
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

    with pytest.raises(InvalidStateTransition, match="task is already DONE"):
        await use_case.execute(request)


@pytest.mark.asyncio
@pytest.mark.uc
async def test_complete_task_generates_next_recurrence(create_use_case_context, fake_uow):
    clock = create_use_case_context["clock"]
    user = User.create(username="wesley")

    # Criamos uma tarefa com regra de recorrência (ex: Diária)
    # Assumindo que você tem uma DailyRecurrenceRule implementada
    task = Task.create(
        title=Title("Treinar"),
        user_id=user.id,
        recurrence=SimpleIntervalRule(frequency=RecurrenceInterval.DAILY, start_date=clock.now()),
        now=clock.now(),
        due_date=clock.now(),
        is_floating=False,
    )

    await fake_uow.users.add(user)
    await fake_uow.tasks.add(task)

    use_case = CompleteTaskUseCase(**create_use_case_context)
    await use_case.execute(TaskByUserRequest(task_id_prefix=str(task.id)[:8], user_id=str(user.id)))

    # Verificação: Deve haver 2 tarefas no repositório agora
    all_tasks = await fake_uow.tasks.find_by_user(user.id)
    assert len(all_tasks) == 2

    # Uma está DONE, a outra está PENDING para o futuro
    statuses = [t.status for t in all_tasks]
    assert TaskStatus.DONE in statuses
    assert TaskStatus.PENDING in statuses
