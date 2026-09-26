"""Tags on tasks, and the inbox (product backlog, Part 7).

The fake clock says 2026-03-05 12:00 UTC (a Thursday); the user is in UTC.
"""

import pytest

from b_domain.entities import Context, User
from b_domain.value_objects import RecurrenceInterval, TaskId
from c_application.dtos.recurrence_dtos import RecurrenceInputDTO
from c_application.dtos.task_dtos import (
    CreateTaskInputDTO,
    ListTasksRequest,
    TaskByUserRequest,
    TaskHistoryRequest,
    TaskOutputDTO,
    UpdateTaskInputDTO,
)
from c_application.use_cases import (
    CompleteTaskUseCase,
    CreateTaskUseCase,
    GetTaskHistoryUseCase,
    ListTasksUseCase,
    UndoPreviewUseCase,
    UndoUseCase,
    UpdateTaskUseCase,
)
from c_application.use_cases.task.undo import UndoRequest
from tests.conftest import FakeUowFactory, UseCaseDeps

pytestmark = [pytest.mark.asyncio, pytest.mark.uc]


@pytest.fixture
async def user(fake_uow_factory: FakeUowFactory) -> User:
    created = User.create(username="wesley", email="wesley@test.com")
    await fake_uow_factory().users.add(created)
    return created


async def _create(deps: UseCaseDeps, user: User, **kwargs: object) -> TaskOutputDTO:
    return await CreateTaskUseCase(**deps).execute(
        CreateTaskInputDTO(user_id=str(user.id), **{"title": "Task", **kwargs})  # type: ignore[arg-type]
    )


async def _edit(
    deps: UseCaseDeps, user: User, task: TaskOutputDTO, **kwargs: object
) -> TaskOutputDTO:
    return await UpdateTaskUseCase(**deps).execute(
        UpdateTaskInputDTO(task_id_prefix=task.id[:8], user_id=str(user.id), **kwargs)  # type: ignore[arg-type]
    )


async def _titles(deps: UseCaseDeps, user: User, **kwargs: object) -> list[str]:
    listed = await ListTasksUseCase(**deps).execute(
        ListTasksRequest(user_id=str(user.id), **kwargs)  # type: ignore[arg-type]
    )
    return sorted(t.title for t in listed.tasks)


# ---------------------------------------------------------------- tags


async def test_tags_on_create_and_in_the_list(
    use_case_context: UseCaseDeps, user: User
) -> None:
    created = await _create(use_case_context, user, title="Buy bread", tags=["#Home"])
    await _create(use_case_context, user, title="Pay rent", tags=["home", "money"])
    await _create(use_case_context, user, title="Call the bank", tags=["money"])

    assert created.tags == ["home"]
    assert await _titles(use_case_context, user, tags=["home"]) == [
        "Buy bread",
        "Pay rent",
    ]
    # Every tag asked for
    assert await _titles(use_case_context, user, tags=["#home", "money"]) == [
        "Pay rent"
    ]


async def test_tags_added_removed_or_replaced(
    use_case_context: UseCaseDeps, user: User
) -> None:
    task = await _create(use_case_context, user, tags=["home"])

    added = await _edit(use_case_context, user, task, add_tags=["urgent, money"])
    removed = await _edit(use_case_context, user, task, remove_tags=["#home"])
    replaced = await _edit(use_case_context, user, task, tags=["work"])
    cleared = await _edit(use_case_context, user, task, tags=[])

    assert added.tags == ["home", "money", "urgent"]
    assert removed.tags == ["money", "urgent"]
    assert replaced.tags == ["work"]
    assert cleared.tags == []


async def test_a_tag_edit_is_in_the_history_and_undone(
    use_case_context: UseCaseDeps, user: User
) -> None:
    task = await _create(use_case_context, user, tags=["home"])
    await _edit(use_case_context, user, task, add_tags=["urgent"])

    history = await GetTaskHistoryUseCase(**use_case_context).execute(
        TaskHistoryRequest(task_id_prefix=task.id[:8], user_id=str(user.id))
    )
    preview = await UndoPreviewUseCase(**use_case_context).execute(
        UndoRequest(user_id=str(user.id))
    )
    await UndoUseCase(**use_case_context).execute(
        UndoRequest(user_id=str(user.id), entry_id=preview.entry_id)
    )

    assert [(c.field, c.before, c.after) for c in history.entries[-1].changes] == [
        ("tags", "#home", "#home #urgent")
    ]
    assert await _titles(use_case_context, user, tags=["urgent"]) == []


async def test_the_next_occurrence_keeps_the_tags(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    created = await _create(
        use_case_context,
        user,
        tags=["health"],
        recurrence=RecurrenceInputDTO(frequency=RecurrenceInterval.DAILY),
    )
    async with fake_uow_factory() as uow:
        task = await uow.tasks.get_by_id(TaskId.from_string(created.id))
    assert task is not None

    following = task.create_next_occurrence(task.created_at)

    assert following is not None
    assert following.tags == {"health"}


# ---------------------------------------------------------------- inbox


async def test_the_inbox_is_what_has_no_date_and_no_context(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    work = Context.create(now=user.created_at, user_id=user.id, name="Work")
    await fake_uow_factory().contexts.add(work)
    user.switch_context(user.created_at, work.id)

    # The active context gets new tasks, unless they go to the inbox
    await _create(use_case_context, user, title="In Work")
    idea = await _create(
        use_case_context, user, title="An idea", use_active_context=False
    )
    await _create(
        use_case_context,
        user,
        title="Dated",
        use_active_context=False,
        due_date="tomorrow",
    )
    done = await _create(
        use_case_context, user, title="Old idea", use_active_context=False
    )
    await CompleteTaskUseCase(**use_case_context).execute(
        TaskByUserRequest(task_id_prefix=done.id[:8], user_id=str(user.id))
    )

    assert idea.context_id is None
    # The active context does not limit the inbox; closed tasks are out
    assert await _titles(
        use_case_context, user, inbox=True, use_active_context=True
    ) == ["An idea"]
