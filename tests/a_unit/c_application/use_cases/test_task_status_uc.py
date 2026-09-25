"""Reopen, archive and cancel: the use cases around the entity's rules."""

import pytest

from a_core import EntityNotFound, InvalidStateTransition
from b_domain.entities import Task, User
from b_domain.exceptions import NotRecurringTaskError
from b_domain.value_objects import TaskStatus, Title
from c_application.dtos.task_dtos import CancelTaskInputDTO, TaskByUserRequest
from c_application.use_cases import (
    ArchiveTaskUseCase,
    CancelTaskUseCase,
    ReopenTaskUseCase,
)
from tests.conftest import FakeClock, FakeUowFactory, UseCaseDeps

pytestmark = [pytest.mark.asyncio, pytest.mark.uc]


async def _stored_task(
    fake_uow_factory: FakeUowFactory, fake_clock: FakeClock, status: TaskStatus
) -> tuple[User, Task]:
    user = User.create(username="wesley", email="wesley@test.com")
    task = Task.create(now=fake_clock.now(), user_id=user.id, title=Title("Report"))
    task.status = status
    async with fake_uow_factory() as uow:
        await uow.users.add(user)
        await uow.tasks.add(task)
    return user, task


def _by_user(user: User, task: Task) -> TaskByUserRequest:
    return TaskByUserRequest(task_id_prefix=str(task.id)[:8], user_id=str(user.id))


async def test_reopen_brings_a_done_task_back(
    fake_uow_factory: FakeUowFactory,
    fake_clock: FakeClock,
    use_case_context: UseCaseDeps,
) -> None:
    user, task = await _stored_task(fake_uow_factory, fake_clock, TaskStatus.DONE)

    out = await ReopenTaskUseCase(**use_case_context).execute(_by_user(user, task))

    assert out.task.id == str(task.id)
    assert out.task.status == TaskStatus.REOPENED
    assert task.status == TaskStatus.REOPENED


async def test_archive_puts_a_cancelled_task_away(
    fake_uow_factory: FakeUowFactory,
    fake_clock: FakeClock,
    use_case_context: UseCaseDeps,
) -> None:
    user, task = await _stored_task(fake_uow_factory, fake_clock, TaskStatus.CANCELLED)

    out = await ArchiveTaskUseCase(**use_case_context).execute(_by_user(user, task))

    assert out.task.status == TaskStatus.ARCHIVED


async def test_archive_refuses_an_open_task(
    fake_uow_factory: FakeUowFactory,
    fake_clock: FakeClock,
    use_case_context: UseCaseDeps,
) -> None:
    user, task = await _stored_task(fake_uow_factory, fake_clock, TaskStatus.PENDING)

    with pytest.raises(InvalidStateTransition):
        await ArchiveTaskUseCase(**use_case_context).execute(_by_user(user, task))
    assert task.status == TaskStatus.PENDING


async def test_cancel_closes_an_open_task(
    fake_uow_factory: FakeUowFactory,
    fake_clock: FakeClock,
    use_case_context: UseCaseDeps,
) -> None:
    user, task = await _stored_task(fake_uow_factory, fake_clock, TaskStatus.PENDING)

    out = await CancelTaskUseCase(**use_case_context).execute(
        CancelTaskInputDTO(task_id_prefix=str(task.id)[:8], user_id=str(user.id))
    )

    assert out.task.status == TaskStatus.CANCELLED


async def test_cancel_refuses_to_end_the_series_of_a_one_off_task(
    fake_uow_factory: FakeUowFactory,
    fake_clock: FakeClock,
    use_case_context: UseCaseDeps,
) -> None:
    user, task = await _stored_task(fake_uow_factory, fake_clock, TaskStatus.PENDING)

    with pytest.raises(NotRecurringTaskError):
        await CancelTaskUseCase(**use_case_context).execute(
            CancelTaskInputDTO(
                task_id_prefix=str(task.id)[:8], user_id=str(user.id), end_series=True
            )
        )


async def test_another_users_task_is_not_found(
    fake_uow_factory: FakeUowFactory,
    fake_clock: FakeClock,
    use_case_context: UseCaseDeps,
) -> None:
    _, task = await _stored_task(fake_uow_factory, fake_clock, TaskStatus.DONE)
    stranger = User.create(username="other", email="other@test.com")

    with pytest.raises(EntityNotFound):
        await ReopenTaskUseCase(**use_case_context).execute(_by_user(stranger, task))
