"""The task history: every change leaves an entry, written with the change."""

from datetime import datetime

import pytest

from b_domain.entities import User
from b_domain.events.registry import EVENT_REGISTRY
from b_domain.events.task_events import TaskEditedEvent
from b_domain.value_objects import TaskId, UserId
from b_domain.value_objects.task_history import TaskAction
from c_application.dtos.task_dtos import (
    CancelTaskInputDTO,
    CreateTaskInputDTO,
    TaskByUserRequest,
    TaskHistoryOutputDTO,
    TaskOutputDTO,
    UpdateTaskInputDTO,
)
from c_application.use_cases import (
    ArchiveTaskUseCase,
    CancelTaskUseCase,
    CompleteTaskUseCase,
    CreateTaskUseCase,
    DeleteTaskUseCase,
    GetTaskHistoryUseCase,
    ReopenTaskUseCase,
    UpdateTaskUseCase,
)
from c_application.use_cases.task.delete import DeleteTaskInputDTO
from tests.conftest import FakeUowFactory, UseCaseDeps

pytestmark = [pytest.mark.asyncio, pytest.mark.uc]


@pytest.fixture
async def user(fake_uow_factory: FakeUowFactory) -> User:
    created = User.create(username="wesley", email="wesley@test.com")
    await fake_uow_factory().users.add(created)
    return created


async def _create(deps: UseCaseDeps, user: User, **kwargs: object) -> TaskOutputDTO:
    return await CreateTaskUseCase(**deps).execute(
        CreateTaskInputDTO(user_id=str(user.id), title="Report", **kwargs)  # type: ignore[arg-type]
    )


def _by(user: User, task: TaskOutputDTO) -> TaskByUserRequest:
    return TaskByUserRequest(task_id_prefix=task.id[:8], user_id=str(user.id))


async def _history(
    deps: UseCaseDeps, user: User, task: TaskOutputDTO
) -> TaskHistoryOutputDTO:
    return await GetTaskHistoryUseCase(**deps).execute(_by(user, task))


async def test_the_life_of_a_task(use_case_context: UseCaseDeps, user: User) -> None:
    task = await _create(use_case_context, user, due_date="2026-03-10 08:00")
    await UpdateTaskUseCase(**use_case_context).execute(
        UpdateTaskInputDTO(
            task_id_prefix=task.id[:8],
            user_id=str(user.id),
            title="Final report",
            due_date="2026-03-12 08:00",
            priority="high",
        )
    )
    done = await CompleteTaskUseCase(**use_case_context).execute(_by(user, task))
    assert done.completed_task.completed_at is not None
    reopened = await ReopenTaskUseCase(**use_case_context).execute(_by(user, task))
    assert reopened.task.completed_at is None
    await CancelTaskUseCase(**use_case_context).execute(
        CancelTaskInputDTO(task_id_prefix=task.id[:8], user_id=str(user.id))
    )
    await ArchiveTaskUseCase(**use_case_context).execute(_by(user, task))

    history = await _history(use_case_context, user, task)

    assert [e.action for e in history.entries] == [
        "created",
        "edited",
        "completed",
        "reopened",
        "cancelled",
        "archived",
    ]
    edit = history.entries[1]
    assert {(c.field, c.before, c.after) for c in edit.changes} == {
        ("title", "Report", "Final report"),
        ("due", "2026-03-10T08:00:00", "2026-03-12T08:00:00"),
        ("priority", "medium", "high"),
    }


async def test_an_edit_that_changes_nothing_leaves_nothing(
    use_case_context: UseCaseDeps, user: User
) -> None:
    task = await _create(use_case_context, user)

    await UpdateTaskUseCase(**use_case_context).execute(
        UpdateTaskInputDTO(
            task_id_prefix=task.id[:8], user_id=str(user.id), title="Report"
        )
    )

    history = await _history(use_case_context, user, task)
    assert [e.action for e in history.entries] == ["created"]


async def test_ending_a_series_is_noted(
    use_case_context: UseCaseDeps, user: User
) -> None:
    from b_domain.value_objects import RecurrenceInterval
    from c_application.dtos.recurrence_dtos import RecurrenceInputDTO

    task = await _create(
        use_case_context,
        user,
        recurrence=RecurrenceInputDTO(frequency=RecurrenceInterval.DAILY),
    )
    await CancelTaskUseCase(**use_case_context).execute(
        CancelTaskInputDTO(
            task_id_prefix=task.id[:8], user_id=str(user.id), end_series=True
        )
    )

    history = await _history(use_case_context, user, task)
    assert history.entries[-1].note == "The series ends here."


async def test_the_history_of_a_deleted_task_stays(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    task = await _create(use_case_context, user)

    await DeleteTaskUseCase(**use_case_context).execute(
        DeleteTaskInputDTO(task_id_prefix=task.id[:8], user_id=str(user.id))
    )

    async with fake_uow_factory() as uow:
        entries = await uow.task_history.list_for_task(
            TaskId.from_string(task.id), user.id
        )
    assert [e.action for e in entries] == [TaskAction.CREATED, TaskAction.DELETED]
    assert entries[-1].note == "Report"


async def test_another_users_history_is_not_read(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    task = await _create(use_case_context, user)

    async with fake_uow_factory() as uow:
        assert (
            await uow.task_history.list_for_task(TaskId.from_string(task.id), UserId())
            == []
        )


@pytest.mark.filterwarnings("ignore::pytest.PytestWarning")
def test_every_event_is_in_the_registry_and_reads_back() -> None:
    assert "TaskEditedEvent" in EVENT_REGISTRY
    edited = TaskEditedEvent(
        occurred_at=datetime(2026, 3, 5, 12, 0),
        task_id=TaskId(),
        user_id=UserId(),
        changes={"title": ["Draft", "Final"], "context": [None, "Work"]},
    )

    back = EVENT_REGISTRY["TaskEditedEvent"].from_dict(edited.to_payload())

    assert type(back) is TaskEditedEvent
    assert back.to_payload() == edited.to_payload()
