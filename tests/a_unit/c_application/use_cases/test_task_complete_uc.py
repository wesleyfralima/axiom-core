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

    # In the DTO, user_id usually arrives as a string from the API/CLI;
    # the use case converts or validates it as needed.
    request = TaskByUserRequest(
        task_id_prefix=str(task.id)[:8],
        user_id=str(user.id),
        completed_at=fake_clock.now(),
    )

    # 3. Execution
    result = await use_case.execute(request)

    # 4. Assertions
    # Check the status through the Enum/ValueObject
    assert result.completed_task.status == TaskStatus.DONE

    # Check that the task in the repository was really updated
    updated_task: Task | None = await uow.tasks.get_by_id(task.id)

    assert updated_task is not None
    assert updated_task.status == TaskStatus.DONE

    # Verificamos a atomicidade
    assert uow.committed is True
    assert uow.rolled_back is False


# -------------------------------------------------------------------------
# 1. Error: prefix too short
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
# 2. Error: ambiguous ID (several tasks with the same prefix)
# -------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.uc
async def test_complete_task_fails_if_prefix_is_ambiguous(
    fake_clock: FakeClock, fake_uow_factory: FakeUowFactory
) -> None:
    user = User.create(username="wesley", email="wesley@test.com")
    now = fake_clock.now()

    # Two tasks starting with the same TaskId
    # The ID is forced so the test is deterministic
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
        # Simulate the scenario in the fake repository
        await uow.tasks.add(t1)
        await uow.tasks.add(t2)

        use_case = CompleteTaskUseCase(clock=fake_clock, uow_factory=fake_uow_factory)
        request = TaskByUserRequest(task_id_prefix=str(t1.id)[:4], user_id=str(user.id))
        # A prefix that would (in theory)
        # match both if they had similar IDs
        # In the fake, find_by_id_prefix must be set up to return both

        # If the fake repository returns more than one, the UC must refuse
        with pytest.raises(ValidationException, match="Ambiguous prefix"):
            await use_case.execute(request)


# -------------------------------------------------------------------------
# 3. Business rule: blocked by dependencies
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

        # Try to complete B without completing A first
        request = TaskByUserRequest(
            task_id_prefix=str(task_b.id)[:8], user_id=str(user.id)
        )

        with pytest.raises(
            DomainException, match="Cannot change task status from blocked to done"
        ):
            await use_case.execute(request)


# -------------------------------------------------------------------------
# 4. Social flow: stop active timers and unblock the next one
# -------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.uc
async def test_complete_task_fails_if_belongs_to_another_user(
    fake_clock: FakeClock, fake_uow_factory: FakeUowFactory
) -> None:
    now = fake_clock.now()

    # Setup: the task belongs to 'other'
    wesley = User.create(username="wesley", email="wesley@test.com")
    other = User.create(username="other", email="wesley@test.com")
    other_task = Task.create(title=Title("Secret task"), user_id=other.id, now=now)

    await fake_uow_factory().tasks.add(other_task)
    await fake_uow_factory().users.add(wesley)

    use_case = CompleteTaskUseCase(clock=fake_clock, uow_factory=fake_uow_factory)

    # Wesley tries to complete it using the other user's task prefix
    request = TaskByUserRequest(
        task_id_prefix=str(other_task.id)[:8],
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
    task = Task.create(title=Title("Already done"), user_id=user.id, now=now)
    task.mark_as_done(fake_clock.now())  # force the DONE state

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
