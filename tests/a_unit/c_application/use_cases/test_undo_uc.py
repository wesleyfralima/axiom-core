"""Undo, restore and deleted tasks as tombstones."""

from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest

from a_core import DomainException
from a_core.exceptions import EntityNotFound, ValidationException
from b_domain.entities import User
from b_domain.value_objects import RecurrenceInterval, TaskId, TaskStatus, UserId
from b_domain.value_objects.sync import Hlc, SyncState
from b_domain.value_objects.task_history import TaskAction, TaskHistoryEntry
from c_application.dtos.recurrence_dtos import RecurrenceInputDTO
from c_application.dtos.task_dtos import (
    CreateTaskInputDTO,
    ListTasksRequest,
    TaskByUserRequest,
    TaskOutputDTO,
    UpdateTaskInputDTO,
)
from c_application.use_cases import (
    CompleteTaskUseCase,
    CreateTaskUseCase,
    DeleteTaskUseCase,
    ListTasksUseCase,
    RestoreTaskUseCase,
    UndoPreviewUseCase,
    UndoUseCase,
    UpdateTaskUseCase,
)
from c_application.use_cases.task.delete import DeleteTaskInputDTO
from c_application.use_cases.task.undo import UndoRequest
from tests.conftest import FakeClock, FakeUowFactory, UseCaseDeps

pytestmark = [pytest.mark.asyncio, pytest.mark.uc]


@pytest.fixture
async def user(fake_uow_factory: FakeUowFactory) -> User:
    created = User.create(username="wesley", email="wesley@test.com")
    await fake_uow_factory().users.add(created)
    return created


async def _create(deps: UseCaseDeps, user: User, **kwargs: object) -> TaskOutputDTO:
    return await CreateTaskUseCase(**deps).execute(
        CreateTaskInputDTO(user_id=str(user.id), **{"title": "Report", **kwargs})  # type: ignore[arg-type]
    )


def _by(user: User, task: TaskOutputDTO) -> TaskByUserRequest:
    return TaskByUserRequest(task_id_prefix=task.id[:8], user_id=str(user.id))


async def _titles(deps: UseCaseDeps, user: User, **kwargs: object) -> list[str]:
    listed = await ListTasksUseCase(**deps).execute(
        ListTasksRequest(user_id=str(user.id), **kwargs)  # type: ignore[arg-type]
    )
    return sorted(t.title for t in listed.tasks)


async def _undo(deps: UseCaseDeps, user: User) -> str:
    preview = await UndoPreviewUseCase(**deps).execute(
        UndoRequest(user_id=str(user.id))
    )
    assert preview.entry_id is not None
    done = await UndoUseCase(**deps).execute(
        UndoRequest(user_id=str(user.id), entry_id=preview.entry_id)
    )
    return done.action


async def _task(fake_uow_factory: FakeUowFactory, task: TaskOutputDTO):  # type: ignore[no-untyped-def]
    async with fake_uow_factory() as uow:
        return await uow.tasks.get_by_id(TaskId.from_string(task.id))


# ---------------------------------------------------------------- tombstones


async def test_a_deleted_task_leaves_the_lists_and_comes_back(
    use_case_context: UseCaseDeps, user: User
) -> None:
    task = await _create(use_case_context, user)

    deleted = await DeleteTaskUseCase(**use_case_context).execute(
        DeleteTaskInputDTO(task_id_prefix=task.id[:8], user_id=str(user.id))
    )
    assert deleted.kept_days == 30
    assert await _titles(use_case_context, user) == []
    assert await _titles(use_case_context, user, deleted=True) == ["Report"]

    restored = await RestoreTaskUseCase(**use_case_context).execute(_by(user, task))
    assert restored.task.title == "Report"
    assert await _titles(use_case_context, user) == ["Report"]


async def test_only_a_deleted_task_can_be_restored(
    use_case_context: UseCaseDeps, user: User
) -> None:
    task = await _create(use_case_context, user)

    with pytest.raises(EntityNotFound):
        await RestoreTaskUseCase(**use_case_context).execute(_by(user, task))


async def test_keep_deleted_days_zero_deletes_for_good(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    user.preferences = user.preferences.update(keep_deleted_days=0)
    task = await _create(use_case_context, user)

    await DeleteTaskUseCase(**use_case_context).execute(
        DeleteTaskInputDTO(task_id_prefix=task.id[:8], user_id=str(user.id))
    )

    assert await _task(fake_uow_factory, task) is None


async def test_deleting_a_blocker_unblocks_its_dependents(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    blocker = await _create(use_case_context, user, title="Before")
    after = await _create(
        use_case_context, user, title="After", depends_on={blocker.id}
    )
    assert after.is_blocked

    await DeleteTaskUseCase(**use_case_context).execute(
        DeleteTaskInputDTO(task_id_prefix=blocker.id[:8], user_id=str(user.id))
    )
    # The fake bus runs no handlers: what the wiring subscribes is checked in
    # enterprise; here, the handler itself
    from b_domain.events.task_events import TaskDeletedEvent
    from c_application.handlers.task_handlers.unlock_task_dependencies_handler import (
        UnlockTaskDependenciesHandler,
    )

    await UnlockTaskDependenciesHandler(fake_uow_factory(), FakeClock()).handle(
        TaskDeletedEvent(
            task_id=TaskId.from_string(blocker.id), user_id=user.id, title="Before"
        )
    )
    back = await _task(fake_uow_factory, after)
    assert back is not None and not back.is_blocked


# ---------------------------------------------------------------- undo


async def test_nothing_to_undo(use_case_context: UseCaseDeps, user: User) -> None:
    preview = await UndoPreviewUseCase(**use_case_context).execute(
        UndoRequest(user_id=str(user.id))
    )
    assert preview.entry is None
    with pytest.raises(ValidationException, match="Nothing to undo"):
        await UndoUseCase(**use_case_context).execute(UndoRequest(user_id=str(user.id)))


async def test_undo_walks_back_one_change_at_a_time(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    task = await _create(use_case_context, user, due_date="2026-03-10 08:00")
    await UpdateTaskUseCase(**use_case_context).execute(
        UpdateTaskInputDTO(
            task_id_prefix=task.id[:8],
            user_id=str(user.id),
            title="Final",
            due_date="2026-03-12 09:00",
        )
    )
    await CompleteTaskUseCase(**use_case_context).execute(_by(user, task))

    assert await _undo(use_case_context, user) == "completed"
    back = await _task(fake_uow_factory, task)
    assert back is not None
    assert back.status == TaskStatus.PENDING and back.completed_at is None
    assert str(back.title) == "Final"

    assert await _undo(use_case_context, user) == "edited"
    back = await _task(fake_uow_factory, task)
    assert back is not None and back.due_date is not None
    assert str(back.title) == "Report"
    assert back.due_date.value.hour == 8

    assert await _undo(use_case_context, user) == "created"
    assert await _titles(use_case_context, user) == []


async def test_undoing_a_completion_takes_away_the_next_occurrence(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    task = await _create(
        use_case_context,
        user,
        title="Gym",
        recurrence=RecurrenceInputDTO(
            frequency=RecurrenceInterval.DAILY, start_date="2026-03-06 07:00"
        ),
    )
    original = await _task(fake_uow_factory, task)
    assert original is not None
    # What the handler does after a completion, linked to it
    await CompleteTaskUseCase(**use_case_context).execute(_by(user, task))
    async with fake_uow_factory() as uow:
        [completion] = [
            e
            for e in await uow.task_history.recent(user.id)
            if e.action == TaskAction.COMPLETED
        ]
    from a_core import UniqueId
    from b_domain.events.task_events import TaskCompletedEvent
    from c_application.handlers.task_handlers.create_recurring_task_handler import (
        CreateRecurringTaskHandler,
    )

    event = TaskCompletedEvent(
        id=UniqueId(completion.entry_id),
        occurred_at=completion.occurred_at,
        task_id=TaskId.from_string(task.id),
        user_id=user.id,
        estimated_minutes=30,
        actual_minutes=0,
        energy_level_used=original.required_energy_level,
        task_complexity=original.complexity,
    )
    await CreateRecurringTaskHandler(fake_uow_factory()).handle(event)
    # The done one and the next one
    assert await _titles(use_case_context, user, include_closed=False) == ["Gym"]

    preview = await UndoPreviewUseCase(**use_case_context).execute(
        UndoRequest(user_id=str(user.id))
    )
    assert preview.also == ["Gym"]
    await _undo(use_case_context, user)

    back = await _task(fake_uow_factory, task)
    assert back is not None
    assert back.status == TaskStatus.PENDING
    assert back.recurrence is not None  # the rule came back too
    # Only the original, open again: the next one is gone
    assert await _titles(use_case_context, user) == ["Gym"]


async def test_undo_brings_a_deleted_task_back(
    use_case_context: UseCaseDeps, user: User
) -> None:
    task = await _create(use_case_context, user)
    await DeleteTaskUseCase(**use_case_context).execute(
        DeleteTaskInputDTO(task_id_prefix=task.id[:8], user_id=str(user.id))
    )

    assert await _undo(use_case_context, user) == "deleted"
    assert await _titles(use_case_context, user) == ["Report"]


async def test_undo_refuses_if_something_changed_since_the_preview(
    use_case_context: UseCaseDeps, user: User
) -> None:
    task = await _create(use_case_context, user)
    preview = await UndoPreviewUseCase(**use_case_context).execute(
        UndoRequest(user_id=str(user.id))
    )
    await CompleteTaskUseCase(**use_case_context).execute(_by(user, task))

    with pytest.raises(ValidationException, match="Something changed since"):
        await UndoUseCase(**use_case_context).execute(
            UndoRequest(user_id=str(user.id), entry_id=preview.entry_id)
        )


async def test_changes_from_before_undo_existed_cannot_be_undone(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    task = await _create(use_case_context, user)
    async with fake_uow_factory() as uow:
        await uow.task_history.add_many(
            [
                TaskHistoryEntry(
                    task_id=TaskId.from_string(task.id),
                    user_id=user.id,
                    occurred_at=FakeClock().now(),
                    action=TaskAction.COMPLETED,
                    note="approximate: before the history existed",
                )
            ]
        )

    preview = await UndoPreviewUseCase(**use_case_context).execute(
        UndoRequest(user_id=str(user.id))
    )
    assert preview.blocked is not None
    assert "before undo existed" in preview.blocked
    with pytest.raises(DomainException, match="before undo existed"):
        await UndoUseCase(**use_case_context).execute(UndoRequest(user_id=str(user.id)))


async def test_another_users_changes_are_not_undone(
    use_case_context: UseCaseDeps, user: User
) -> None:
    await _create(use_case_context, user)

    preview = await UndoPreviewUseCase(**use_case_context).execute(
        UndoRequest(user_id=str(UserId()))
    )
    assert preview.entry is None


# --------------------------------------------------------------------- sync


async def test_undo_leaves_the_changes_other_devices_made(
    use_case_context: UseCaseDeps, fake_uow_factory: FakeUowFactory, user: User
) -> None:
    mine, other = uuid4(), uuid4()
    uow = fake_uow_factory()
    uow.sync.sync_state = SyncState(
        server_url="https://example.com",
        account_id=user.id.value,
        device_id=mine,
        device_name="mint",
        clock=Hlc.start(mine),
    )
    task = await _create(use_case_context, user, title="Mine")
    # The history's storage stamps each change with its device
    history = uow.task_history.entries
    history[:] = [replace(e, device_id=mine) for e in history]
    history.append(
        replace(
            history[-1],
            entry_id=uuid4(),
            action=TaskAction.EDITED,
            occurred_at=history[-1].occurred_at + timedelta(minutes=1),
            device_id=other,
        )
    )

    preview = await UndoPreviewUseCase(**use_case_context).execute(
        UndoRequest(user_id=str(user.id))
    )

    assert preview.task_id == task.id
    assert preview.entry is not None
    assert preview.entry.action == str(TaskAction.CREATED)
