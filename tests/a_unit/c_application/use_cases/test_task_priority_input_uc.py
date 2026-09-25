"""Prioridade/complexidade digitadas pelo usuário chegam como texto."""

import pytest

from a_core.exceptions import InvalidValueError
from b_domain.entities import Task, User, UserPrefs
from b_domain.ports.unit_of_work import UowFactoryType
from b_domain.value_objects import Priority, Title
from b_domain.value_objects.enums import TaskComplexity
from c_application.dtos import CreateTaskInputDTO
from c_application.dtos.task_dtos import ListTasksRequest, UpdateTaskInputDTO
from c_application.use_cases import (
    CreateTaskUseCase,
    ListTasksUseCase,
    UpdateTaskUseCase,
)
from tests.conftest import FakeClock

pytestmark = [pytest.mark.asyncio, pytest.mark.uc]


async def _user_with_tasks(uow_factory: UowFactoryType, now) -> tuple[User, Task]:
    user = User.create(username="wesley", email="w@test.com")
    high = Task.create(
        now=now,
        user_id=user.id,
        title=Title("Alta"),
        priority=Priority.HIGH,
        complexity=TaskComplexity.VERY_HIGH,
    )
    low = Task.create(now=now, user_id=user.id, title=Title("Baixa"))
    async with uow_factory() as uow:
        await uow.users.add(user)
        await uow.tasks.add(high)
        await uow.tasks.add(low)
    return user, high


async def test_list_filters_by_priority_name(
    fake_uow_factory: UowFactoryType, fake_clock: FakeClock
) -> None:
    user, high = await _user_with_tasks(fake_uow_factory, fake_clock.now())

    result = await ListTasksUseCase(fake_uow_factory, fake_clock).execute(
        ListTasksRequest(user_id=str(user.id), priority="high")
    )

    assert [t.id for t in result.tasks] == [str(high.id)]


async def test_list_filters_by_complexity_name(
    fake_uow_factory: UowFactoryType, fake_clock: FakeClock
) -> None:
    user, high = await _user_with_tasks(fake_uow_factory, fake_clock.now())

    result = await ListTasksUseCase(fake_uow_factory, fake_clock).execute(
        ListTasksRequest(user_id=str(user.id), complexity="very-high")
    )

    assert [t.id for t in result.tasks] == [str(high.id)]


async def test_list_rejects_unknown_priority(
    fake_uow_factory: UowFactoryType, fake_clock: FakeClock
) -> None:
    user, _ = await _user_with_tasks(fake_uow_factory, fake_clock.now())

    with pytest.raises(InvalidValueError, match="urgent"):
        await ListTasksUseCase(fake_uow_factory, fake_clock).execute(
            ListTasksRequest(user_id=str(user.id), priority="urgent")
        )


async def test_update_without_priority_keeps_it(
    fake_uow_factory: UowFactoryType, fake_clock: FakeClock
) -> None:
    user, high = await _user_with_tasks(fake_uow_factory, fake_clock.now())

    result = await UpdateTaskUseCase(fake_uow_factory, fake_clock).execute(
        UpdateTaskInputDTO(
            task_id_prefix=str(high.id)[:8], user_id=str(user.id), title="Renomeada"
        )
    )

    assert result.title == "Renomeada"
    assert result.priority == "HIGH"


async def test_update_priority_by_name(
    fake_uow_factory: UowFactoryType, fake_clock: FakeClock
) -> None:
    user, high = await _user_with_tasks(fake_uow_factory, fake_clock.now())

    result = await UpdateTaskUseCase(fake_uow_factory, fake_clock).execute(
        UpdateTaskInputDTO(
            task_id_prefix=str(high.id)[:8], user_id=str(user.id), priority="low"
        )
    )

    assert result.priority == "LOW"


async def test_create_without_priority_uses_the_user_default(
    fake_uow_factory: UowFactoryType, fake_clock: FakeClock
) -> None:
    user = User.create(
        username="wesley",
        email="w@test.com",
        preferences=UserPrefs(default_task_priority="critical"),
    )
    async with fake_uow_factory() as uow:
        await uow.users.add(user)

    result = await CreateTaskUseCase(fake_uow_factory, fake_clock).execute(
        CreateTaskInputDTO(user_id=str(user.id), title="Sem prioridade")
    )

    assert result.priority == "CRITICAL"


async def test_create_with_explicit_priority(
    fake_uow_factory: UowFactoryType, fake_clock: FakeClock
) -> None:
    user = User.create(username="wesley", email="w@test.com")
    async with fake_uow_factory() as uow:
        await uow.users.add(user)

    result = await CreateTaskUseCase(fake_uow_factory, fake_clock).execute(
        CreateTaskInputDTO(user_id=str(user.id), title="Com prioridade", priority=3)
    )

    assert result.priority == "HIGH"


async def _user_with_done_task(uow_factory: UowFactoryType, now) -> tuple[User, Task]:
    user, open_task = await _user_with_tasks(uow_factory, now)
    done = Task.create(now=now, user_id=user.id, title=Title("Feita"))
    done.mark_as_done(now)
    async with uow_factory() as uow:
        await uow.tasks.add(done)
    return user, done


async def test_list_can_hide_closed_tasks(
    fake_uow_factory: UowFactoryType, fake_clock: FakeClock
) -> None:
    user, done = await _user_with_done_task(fake_uow_factory, fake_clock.now())
    use_case = ListTasksUseCase(fake_uow_factory, fake_clock)

    everything = await use_case.execute(ListTasksRequest(user_id=str(user.id)))
    open_only = await use_case.execute(
        ListTasksRequest(user_id=str(user.id), include_closed=False)
    )

    assert str(done.id) in [t.id for t in everything.tasks]
    assert str(done.id) not in [t.id for t in open_only.tasks]
    assert len(open_only.tasks) == 2


async def test_explicit_status_wins_over_hiding_closed(
    fake_uow_factory: UowFactoryType, fake_clock: FakeClock
) -> None:
    user, done = await _user_with_done_task(fake_uow_factory, fake_clock.now())

    result = await ListTasksUseCase(fake_uow_factory, fake_clock).execute(
        ListTasksRequest(user_id=str(user.id), status="done", include_closed=False)
    )

    assert [t.id for t in result.tasks] == [str(done.id)]
