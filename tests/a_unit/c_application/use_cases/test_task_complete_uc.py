from dataclasses import dataclass, replace
from uuid import uuid4

import pytest

from a_core import DomainException, ValidationException
from b_domain.entities import Task, User
from b_domain.value_objects import TaskId, TaskStatus, Title
from c_application.dtos.task_dtos import TaskByUserRequest
from c_application.use_cases import CompleteTaskUseCase
from tests.conftest import FakeClock, FakeUowFactory, UseCaseDeps


@pytest.mark.asyncio
@pytest.mark.uc
async def test_complete_task_successfully(
    fake_clock: FakeClock,
    fake_uow_factory: FakeUowFactory,
) -> None:

    user = User.create(username="wesley", email="wesley@test.com")

    # Passamos o user.id (UserId) diretamente
    task = Task.create(
        title=Title("Test Task"),
        user_id=user.id,
        now=fake_clock.now(),
    )

    async with fake_uow_factory() as uow:
        # Populamos o Fake UOW
        await uow.tasks.add(task)
        await uow.users.add(user)

    # 2. Instanciar Use Case
    use_case = CompleteTaskUseCase(clock=fake_clock, uow_factory=fake_uow_factory)

    # No DTO, o user_id costuma vir como string da API/CLI,
    # o Use Case se encarrega de converter ou validar se necessário.
    request = TaskByUserRequest(
        task_id_prefix=str(task.id)[:8],
        user_id=str(user.id),
        completed_at=fake_clock.now(),
    )

    # 3. Execução
    result = await use_case.execute(request)

    # 4. Asserções
    # Verificamos o status através do Enum/ValueObject
    assert result.completed_task.status == TaskStatus.DONE

    # Verificamos se a tarefa no repositório foi realmente atualizada
    updated_task: Task | None = await uow.tasks.get_by_id(task.id)

    assert updated_task is not None
    assert updated_task.status == TaskStatus.DONE

    # Verificamos a atomicidade
    assert uow.committed is True
    assert uow.rolled_back is False


# -------------------------------------------------------------------------
# 1. Erro: Prefixo muito curto
# -------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.uc
async def test_complete_task_fails_if_prefix_too_short(
    create_use_case_context: UseCaseDeps,
) -> None:
    use_case = CompleteTaskUseCase(**create_use_case_context)
    request = TaskByUserRequest(task_id_prefix="abc", user_id=str(uuid4()))

    with pytest.raises(
        ValidationException, match="IdPrefix must have at least 4 characters"
    ):
        await use_case.execute(request)


# -------------------------------------------------------------------------
# 2. Erro: ID Ambíguo (Múltiplas tarefas com mesmo prefixo)
# -------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.uc
async def test_complete_task_fails_if_prefix_is_ambiguous(
    fake_clock: FakeClock, fake_uow_factory: FakeUowFactory
) -> None:
    user = User.create(username="wesley", email="wesley@test.com")
    now = fake_clock.now()

    # Criamos duas tarefas que começam com o mesmo TaskId
    # Forçamos o ID para o teste ser determinístico
    tid = TaskId()

    @dataclass(eq=True)
    class FakeId:
        value: str

        def __hash__(self) -> int:
            return hash(self.value)

        def __str__(self) -> str:
            return self.value

    same_id = FakeId(str(tid)[:30])

    t1 = Task.create(title=Title("Task 1"), user_id=user.id, now=now)
    t1 = replace(t1, id=tid)
    t2 = Task.create(title=Title("Task 2"), user_id=user.id, now=now)
    # A non-TaskId on purpose: the fake repository only compares strings
    t2 = replace(t2, id=same_id)  # type: ignore[arg-type]

    async with fake_uow_factory() as uow:
        # Simulamos o cenário no fake repositório
        await uow.tasks.add(t1)
        await uow.tasks.add(t2)

        use_case = CompleteTaskUseCase(clock=fake_clock, uow_factory=fake_uow_factory)
        request = TaskByUserRequest(task_id_prefix=str(t1.id)[:4], user_id=str(user.id))
        # Usamos um prefixo que (teoricamente)
        # bateria em ambas se tivessem IDs similares
        # No fake, o find_by_id_prefix deve ser populado para retornar ambas

        # Se o repositório fake retornar mais de uma, o UC deve barrar
        with pytest.raises(ValidationException, match="Ambiguous prefix"):
            await use_case.execute(request)


# -------------------------------------------------------------------------
# 3. Regra de Negócio: Bloqueio por Dependências
# -------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.uc
async def test_complete_task_fails_if_task_is_blocked(
    fake_clock: FakeClock, fake_uow_factory: FakeUowFactory
) -> None:
    user = User.create(username="wesley", email="wesley@test.com")
    now = fake_clock.now()

    task_a = Task.create(title=Title("Task A"), user_id=user.id, now=now)
    task_b = Task.create(title=Title("Task B"), user_id=user.id, now=now)

    task_b.add_dependency(task_a.id, now)  # B depende de A

    async with fake_uow_factory() as uow:
        await uow.tasks.add(task_a)
        await uow.tasks.add(task_b)
        await uow.users.add(user)

        use_case = CompleteTaskUseCase(clock=fake_clock, uow_factory=fake_uow_factory)

        # Tentar completar B sem completar A antes
        request = TaskByUserRequest(
            task_id_prefix=str(task_b.id)[:8], user_id=str(user.id)
        )

        with pytest.raises(
            DomainException, match="Cannot change task status from blocked to done"
        ):
            await use_case.execute(request)


# -------------------------------------------------------------------------
# 4. Fluxo Social: Parar Timers Ativos e Desbloquear Próxima
# -------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.uc
async def test_complete_task_fails_if_belongs_to_another_user(
    fake_clock: FakeClock, fake_uow_factory: FakeUowFactory
) -> None:
    now = fake_clock.now()

    # Setup: Tarefa pertence ao 'outro'
    wesley = User.create(username="wesley", email="wesley@test.com")
    outro = User.create(username="outro", email="wesley@test.com")
    task_do_outro = Task.create(
        title=Title("Tarefa Secreta"), user_id=outro.id, now=now
    )

    await fake_uow_factory().tasks.add(task_do_outro)
    await fake_uow_factory().users.add(wesley)

    use_case = CompleteTaskUseCase(clock=fake_clock, uow_factory=fake_uow_factory)

    # Wesley tenta completar usando o prefixo da tarefa do outro
    request = TaskByUserRequest(
        task_id_prefix=str(task_do_outro.id)[:8],
        user_id=str(wesley.id),
    )

    with pytest.raises(ValidationException, match="No task found with ID prefix"):
        await use_case.execute(request)


@pytest.mark.asyncio
@pytest.mark.uc
async def test_complete_task_fails_if_already_done(
    fake_clock: FakeClock, fake_uow_factory: FakeUowFactory
) -> None:
    now = fake_clock.now()

    user = User.create(username="wesley", email="wesley@test.com")
    task = Task.create(title=Title("Já fiz"), user_id=user.id, now=now)
    task.mark_as_done(fake_clock.now())  # Forçamos o estado DONE

    async with fake_uow_factory() as uow:
        await uow.tasks.add(task)
        await uow.users.add(user)

        use_case = CompleteTaskUseCase(clock=fake_clock, uow_factory=fake_uow_factory)
        request = TaskByUserRequest(
            task_id_prefix=str(task.id)[:8], user_id=str(user.id)
        )

        with pytest.raises(
            DomainException, match="Cannot change task status from done to done"
        ):
            await use_case.execute(request)


@pytest.mark.asyncio
@pytest.mark.uc
async def test_complete_task_unknown_prefix_says_not_found(
    fake_clock: FakeClock, fake_uow_factory: FakeUowFactory
) -> None:
    user = User.create(username="wesley", email="wesley@test.com")
    async with fake_uow_factory() as uow:
        await uow.users.add(user)

    use_case = CompleteTaskUseCase(clock=fake_clock, uow_factory=fake_uow_factory)
    request = TaskByUserRequest(task_id_prefix="abcd1234", user_id=str(user.id))

    with pytest.raises(ValidationException, match="No task found"):
        await use_case.execute(request)
