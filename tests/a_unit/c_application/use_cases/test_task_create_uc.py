from datetime import UTC, datetime, time, timedelta
from uuid import UUID, uuid4

import pytest

from a_core import ValidationException
from b_domain.entities import Task, User, UserPrefs
from b_domain.value_objects import ContextId, RecurrenceInterval, TaskId, Title
from c_application.dtos import CreateTaskInputDTO
from c_application.dtos.recurrence_dtos import RecurrenceInputDTO
from c_application.use_cases import CreateTaskUseCase
from tests.conftest import FakeClock, FakeUowFactory, UseCaseDeps


@pytest.mark.asyncio
@pytest.mark.uc
async def test_create_task_successfully(
    fake_clock: FakeClock, fake_uow_factory: FakeUowFactory
) -> None:

    async with fake_uow_factory() as uow:
        # 1. Setup
        user = User.create(username="wesley", email="wesley@test.com")
        await uow.users.add(user)

    dto = CreateTaskInputDTO(
        user_id=str(user.id),
        title="Aprender Rust",
        description="Para performance extrema",
        required_energy_level=3,  # High
    )

    # 2. Execução
    use_case = CreateTaskUseCase(uow_factory=fake_uow_factory, clock=fake_clock)
    result = await use_case.execute(dto)

    # 3. Asserções
    assert result.title == "Aprender Rust"
    assert result.status == "pending"
    assert result.required_energy_level == 3

    # Valida persistência e atomicidade
    task_id: TaskId = TaskId(UUID(result.id))
    task_in_db = await uow.tasks.get_by_id(task_id)
    assert task_in_db is not None
    assert uow.committed is True


@pytest.mark.asyncio
@pytest.mark.uc
async def test_create_task_fails_if_title_is_invalid(
    use_case_context: UseCaseDeps,
) -> None:
    # Setup com título que viola a regra do VO Title (ex: vazio ou muito curto)
    use_case = CreateTaskUseCase(**use_case_context)
    dto = CreateTaskInputDTO(user_id=str(uuid4()), title="")

    # O Use Case deve capturar o erro do VO e relançar
    # como ValidationException ou DomainException
    with pytest.raises(ValidationException):
        await use_case.execute(dto)


@pytest.mark.asyncio
@pytest.mark.uc
async def test_create_task_fails_if_user_not_found(
    use_case_context: UseCaseDeps, fake_uow_factory: FakeUowFactory
) -> None:
    use_case = CreateTaskUseCase(**use_case_context)
    dto = CreateTaskInputDTO(
        user_id=str(uuid4()),  # ID aleatório que não está no fake_uow
        title="Tarefa Fantasma",
    )

    with pytest.raises(ValidationException, match="not found"):
        await use_case.execute(dto)


@pytest.mark.asyncio
@pytest.mark.uc
async def test_create_task_inherits_active_context_from_user(
    use_case_context: UseCaseDeps, fake_uow_factory: FakeUowFactory
) -> None:
    # 1. Setup: Usuário com contexto ativo "Trabalho"
    work_context_id: ContextId = ContextId(uuid4())
    prefs = UserPrefs(active_context_id=work_context_id)
    user = User.create(username="wesley", preferences=prefs, email="wesley@test.com")

    await fake_uow_factory().users.add(user)

    # DTO sem contexto explícito
    dto = CreateTaskInputDTO(
        user_id=str(user.id), title="Revisão de PR", context_id=None
    )

    # 2. Execução
    use_case = CreateTaskUseCase(**use_case_context)
    result = await use_case.execute(dto)

    # 3. Asserção: Verificação no "banco" se herdou o contexto
    task_id: TaskId = TaskId(UUID(result.id))
    task_in_db = await fake_uow_factory().tasks.get_by_id(task_id)
    assert task_in_db is not None
    assert task_in_db.context_id == work_context_id


@pytest.mark.asyncio
@pytest.mark.uc
async def test_create_task_with_recurrence_calculates_initial_due_date(
    use_case_context: UseCaseDeps, fake_uow_factory: FakeUowFactory
) -> None:
    clock = use_case_context["clock"]
    user = User.create(username="wesley", email="wesley@test.com")
    await fake_uow_factory().users.add(user)

    # DTO de recorrência diária
    recurrence_dto = RecurrenceInputDTO(
        frequency=RecurrenceInterval.DAILY, interval=1, start_date=clock.now()
    )

    dto = CreateTaskInputDTO(
        user_id=str(user.id),
        title="Meditar",
        due_date=None,  # Deixamos vazio para o motor calcular
        recurrence=recurrence_dto,
    )

    # 2. Execução
    use_case = CreateTaskUseCase(**use_case_context)
    result = await use_case.execute(dto)

    # 3. Asserções
    assert result.due_date is not None
    assert result.recurrence_display is not None

    # Verifica se a data faz sentido
    task_id: TaskId = TaskId(UUID(result.id))
    task_in_db = await fake_uow_factory().tasks.get_by_id(task_id)
    assert task_in_db is not None
    assert task_in_db.recurrence is not None


@pytest.mark.asyncio
@pytest.mark.uc
async def test_create_task_fails_if_parent_belongs_to_another_user(
    use_case_context: UseCaseDeps, fake_uow_factory: FakeUowFactory
) -> None:
    clock = use_case_context["clock"]
    wesley = User.create(username="wesley", email="wesley@test.com")
    outro = User.create(username="outro", email="outro@test.com")

    # Tarefa que pertence ao 'outro'
    task_do_outro = Task.create(
        title=Title("Tarefa Secreta"), user_id=outro.id, now=clock.now()
    )

    async with fake_uow_factory() as uow:
        await uow.users.add(wesley)
        await uow.tasks.add(task_do_outro)

    dto = CreateTaskInputDTO(
        user_id=str(wesley.id),
        title="Minha Sub-tarefa",
        parent_id=str(task_do_outro.id),  # Tentando anexar na tarefa do outro
    )

    use_case = CreateTaskUseCase(**use_case_context)

    with pytest.raises(ValidationException, match="Parent task not found"):
        await use_case.execute(dto)


@pytest.mark.asyncio
@pytest.mark.uc
async def test_create_floating_task_inherits_timezone_from_user_prefs(
    use_case_context: UseCaseDeps, fake_uow_factory: FakeUowFactory
) -> None:
    clock = use_case_context["clock"]
    # Floating must not have a timezone
    now = clock.now().replace(tzinfo=None)

    prefs = UserPrefs(timezone="America/Sao_Paulo")
    user = User.create(username="wesley", preferences=prefs, email="wesley@test.com")
    await fake_uow_factory().users.add(user)

    dto = CreateTaskInputDTO(
        user_id=str(user.id),
        title="Tarefa com fuso herdado",
        due_date=now,
        is_floating=True,
        timezone=None,  # Omissão proposital
    )

    use_case = CreateTaskUseCase(**use_case_context)
    result = await use_case.execute(dto)

    # Verifica na entidade se o fuso foi aplicado
    task_id: TaskId = TaskId(UUID(result.id))
    task_in_db = await fake_uow_factory().tasks.get_by_id(task_id)
    assert task_in_db is not None and task_in_db.due_date is not None
    assert task_in_db.due_date.timezone == "America/Sao_Paulo"


@pytest.mark.asyncio
@pytest.mark.uc
async def test_create_fixed_task_user_utc(
    use_case_context: UseCaseDeps, fake_uow_factory: FakeUowFactory
) -> None:
    clock = use_case_context["clock"]
    # Floating must have UTC timezone
    now = clock.now().replace(tzinfo=UTC)

    prefs = UserPrefs(timezone="America/Sao_Paulo")
    user = User.create(username="wesley", preferences=prefs, email="wesley@test.com")
    await fake_uow_factory().users.add(user)

    dto = CreateTaskInputDTO(
        user_id=str(user.id),
        title="Tarefa com fuso herdado",
        due_date=now,
        is_floating=False,  # I.E. it is fixed
        timezone=None,  # Omissão proposital
    )

    use_case = CreateTaskUseCase(**use_case_context)
    result = await use_case.execute(dto)

    # Verifica na entidade se o fuso foi aplicado
    task_id: TaskId = TaskId(UUID(result.id))
    task_in_db = await fake_uow_factory().tasks.get_by_id(task_id)
    assert task_in_db is not None and task_in_db.due_date is not None
    assert task_in_db.due_date.timezone == "UTC"


@pytest.mark.asyncio
@pytest.mark.uc
async def test_create_task_success_if_recurrence_end_date_mismatches_timezone_type(
    use_case_context: UseCaseDeps, fake_uow_factory: FakeUowFactory
) -> None:
    """
    Valida que o Use Case tem sucesso se tentarmos criar uma tarefa flutuante (naive)
    mas passarmos um end_date com fuso horário (aware) na recorrência.
    """

    user = User.create(username="wesley", email="wesley@test.com")
    await fake_uow_factory().users.add(user)

    assert user.id is not None

    # Tarefa Flutuante (is_floating=True) → Deve ser Naive
    # Mas enviamos um end_date Aware (com UTC)
    end_date_aware = datetime.now(UTC) + timedelta(days=30)
    start_date_naive = datetime.now(UTC).replace(tzinfo=None)

    recurrence_dto = RecurrenceInputDTO(
        frequency=RecurrenceInterval.DAILY,
        interval=1,
        start_date=start_date_naive,
        end_date=end_date_aware,
    )

    dto = CreateTaskInputDTO(
        user_id=str(user.id),
        title="Estudar Consciência de Datas",
        is_floating=True,
        recurrence=recurrence_dto,
    )

    use_case = CreateTaskUseCase(**use_case_context)
    await use_case.execute(dto)

    # Se chegou aqui, não houve erros
    assert True


@pytest.mark.asyncio
@pytest.mark.uc
async def test_create_task_keeps_the_hourly_window(
    use_case_context: UseCaseDeps, fake_uow_factory: FakeUowFactory
) -> None:
    """Regression: the window was dropped, leaving "every 2 hours" all day."""

    user = User.create(username="wesley", email="wesley@test.com")
    await fake_uow_factory().users.add(user)

    result = await CreateTaskUseCase(**use_case_context).execute(
        CreateTaskInputDTO(
            user_id=str(user.id),
            title="Beber água",
            recurrence=RecurrenceInputDTO(
                frequency=RecurrenceInterval.HOURLY,
                interval=2,
                start_date=datetime(2026, 3, 5, 8, 0),
                window_start=time(8, 0),
                window_end=time(20, 0),
            ),
        )
    )

    assert result.recurrence_display == "Every 2 hours between 08:00 and 20:00."
