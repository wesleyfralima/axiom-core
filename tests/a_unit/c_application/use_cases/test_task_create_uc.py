from datetime import UTC, datetime, time, timedelta
from uuid import UUID, uuid4

import pytest

from a_core import ValidationException
from a_core.exceptions import EntityNotFound
from b_domain.entities import Context, Task, User, UserPrefs
from b_domain.value_objects import ContextId, RecurrenceInterval, TaskId, Title
from c_application.dtos import CreateTaskInputDTO
from c_application.dtos.recurrence_dtos import RecurrenceInputDTO
from c_application.dtos.task_dtos import ListTasksRequest
from c_application.use_cases import CreateTaskUseCase, ListTasksUseCase
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
        title="Learn Rust",
        description="For extreme performance",
        required_energy_level=3,  # High
    )

    # 2. Execution
    use_case = CreateTaskUseCase(uow_factory=fake_uow_factory, clock=fake_clock)
    result = await use_case.execute(dto)

    # 3. Assertions
    assert result.title == "Learn Rust"
    assert result.status == "pending"
    assert result.required_energy_level == 3

    # Check persistence and atomicity
    task_id: TaskId = TaskId(UUID(result.id))
    task_in_db = await uow.tasks.get_by_id(task_id)
    assert task_in_db is not None
    assert uow.committed is True


@pytest.mark.asyncio
@pytest.mark.uc
async def test_create_task_fails_if_title_is_invalid(
    use_case_context: UseCaseDeps,
) -> None:
    # Setup with a title that breaks the Title VO rule (e.g. empty or too short)
    use_case = CreateTaskUseCase(**use_case_context)
    dto = CreateTaskInputDTO(user_id=str(uuid4()), title="")

    # The use case must catch the VO error and re-raise it
    # as ValidationException or DomainException
    with pytest.raises(ValidationException):
        await use_case.execute(dto)


@pytest.mark.asyncio
@pytest.mark.uc
async def test_create_task_fails_if_user_not_found(
    use_case_context: UseCaseDeps, fake_uow_factory: FakeUowFactory
) -> None:
    use_case = CreateTaskUseCase(**use_case_context)
    dto = CreateTaskInputDTO(
        user_id=str(uuid4()),  # random ID that is not in fake_uow
        title="Ghost task",
    )

    with pytest.raises(ValidationException, match="not found"):
        await use_case.execute(dto)


@pytest.mark.asyncio
@pytest.mark.uc
async def test_create_task_inherits_active_context_from_user(
    use_case_context: UseCaseDeps, fake_uow_factory: FakeUowFactory
) -> None:
    # 1. Setup: user with active context "Work"
    user = User.create(username="wesley", email="wesley@test.com")
    work = Context.create(now=datetime.now(UTC), user_id=user.id, name="Work")
    work_context_id: ContextId = work.id
    user.preferences = UserPrefs(active_context_id=work_context_id)

    await fake_uow_factory().users.add(user)
    await fake_uow_factory().contexts.add(work)

    # DTO without an explicit context
    dto = CreateTaskInputDTO(user_id=str(user.id), title="PR review", context_id=None)

    # 2. Execution
    use_case = CreateTaskUseCase(**use_case_context)
    result = await use_case.execute(dto)

    # 3. Assertion: check in the "database" that the context was inherited
    task_id: TaskId = TaskId(UUID(result.id))
    task_in_db = await fake_uow_factory().tasks.get_by_id(task_id)
    assert task_in_db is not None
    assert task_in_db.context_id == work_context_id
    assert result.context_name == "Work"


@pytest.mark.asyncio
@pytest.mark.uc
async def test_create_task_ignores_an_active_context_that_no_longer_exists(
    use_case_context: UseCaseDeps, fake_uow_factory: FakeUowFactory
) -> None:
    prefs = UserPrefs(active_context_id=ContextId(uuid4()))
    user = User.create(username="wesley", preferences=prefs, email="wesley@test.com")
    await fake_uow_factory().users.add(user)

    result = await CreateTaskUseCase(**use_case_context).execute(
        CreateTaskInputDTO(user_id=str(user.id), title="Orphan")
    )

    assert result.context_id is None


@pytest.mark.asyncio
@pytest.mark.uc
async def test_create_task_with_recurrence_calculates_initial_due_date(
    use_case_context: UseCaseDeps, fake_uow_factory: FakeUowFactory
) -> None:
    clock = use_case_context["clock"]
    user = User.create(username="wesley", email="wesley@test.com")
    await fake_uow_factory().users.add(user)

    # Daily recurrence DTO
    recurrence_dto = RecurrenceInputDTO(
        frequency=RecurrenceInterval.DAILY, interval=1, start_date=clock.now()
    )

    dto = CreateTaskInputDTO(
        user_id=str(user.id),
        title="Meditate",
        due_date=None,  # left empty for the engine to compute
        recurrence=recurrence_dto,
    )

    # 2. Execution
    use_case = CreateTaskUseCase(**use_case_context)
    result = await use_case.execute(dto)

    # 3. Assertions
    assert result.due_date is not None
    assert result.recurrence_display is not None

    # Check that the date makes sense
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
    other = User.create(username="other", email="other@test.com")

    # Task that belongs to 'other'
    other_task = Task.create(
        title=Title("Secret task"), user_id=other.id, now=clock.now()
    )

    async with fake_uow_factory() as uow:
        await uow.users.add(wesley)
        await uow.tasks.add(other_task)

    dto = CreateTaskInputDTO(
        user_id=str(wesley.id),
        title="My subtask",
        parent_id=str(other_task.id),  # trying to attach to the other user's task
    )

    use_case = CreateTaskUseCase(**use_case_context)

    with pytest.raises(EntityNotFound, match="was not found"):
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
        title="Task with inherited timezone",
        due_date=now,
        is_floating=True,
        timezone=None,  # deliberately omitted
    )

    use_case = CreateTaskUseCase(**use_case_context)
    result = await use_case.execute(dto)

    # Check on the entity that the timezone was applied
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
        title="Task with inherited timezone",
        due_date=now,
        is_floating=False,  # I.E. it is fixed
        timezone=None,  # deliberately omitted
    )

    use_case = CreateTaskUseCase(**use_case_context)
    result = await use_case.execute(dto)

    # Check on the entity that the timezone was applied
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
    The use case succeeds when creating a floating (naive) task
    with a timezone-aware end_date in the recurrence.
    """

    user = User.create(username="wesley", email="wesley@test.com")
    await fake_uow_factory().users.add(user)

    assert user.id is not None

    # Floating task (is_floating=True) -> must be naive
    # But we send an aware end_date (UTC)
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
        title="Study date awareness",
        is_floating=True,
        recurrence=recurrence_dto,
    )

    use_case = CreateTaskUseCase(**use_case_context)
    await use_case.execute(dto)

    # Reaching this point means there were no errors
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
            title="Drink water",
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


@pytest.mark.asyncio
@pytest.mark.uc
async def test_parent_and_dependencies_by_id_prefix(
    use_case_context: UseCaseDeps, fake_uow_factory: FakeUowFactory
) -> None:
    wesley = User.create(username="wesley", email="wesley@test.com")
    async with fake_uow_factory() as uow:
        await uow.users.add(wesley)
    create = CreateTaskUseCase(**use_case_context)
    parent = await create.execute(
        CreateTaskInputDTO(user_id=str(wesley.id), title="Move house")
    )
    before = await create.execute(
        CreateTaskInputDTO(user_id=str(wesley.id), title="Before")
    )

    child = await create.execute(
        CreateTaskInputDTO(
            user_id=str(wesley.id),
            title="Pack the books",
            parent_id=parent.id[:4],
            depends_on={before.id[:8].upper()},
        )
    )

    assert child.parent_id == parent.id
    assert child.is_blocked
    listed = await ListTasksUseCase(**use_case_context).execute(
        ListTasksRequest(user_id=str(wesley.id), parent_id=parent.id[:6])
    )
    assert [t.title for t in listed.tasks] == ["Pack the books"]


@pytest.mark.asyncio
@pytest.mark.uc
async def test_a_dependency_must_exist(
    use_case_context: UseCaseDeps, fake_uow_factory: FakeUowFactory
) -> None:
    wesley = User.create(username="wesley", email="wesley@test.com")
    async with fake_uow_factory() as uow:
        await uow.users.add(wesley)

    with pytest.raises(EntityNotFound):
        await CreateTaskUseCase(**use_case_context).execute(
            CreateTaskInputDTO(
                user_id=str(wesley.id),
                title="After",
                depends_on={"071d7f23-e94e-43ba-a0d5-4c912a22e9ba"},
            )
        )
