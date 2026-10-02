"""A task's relations: parent and subtasks, dependencies kept once done."""

from datetime import datetime

import pytest

from a_core.exceptions import InvalidStateTransition, ValidationException
from b_domain.entities import Task, User
from b_domain.events.task_events import (
    TaskCompletedEvent,
    TaskReopenedEvent,
)
from b_domain.value_objects import TaskId, TaskStatus
from b_domain.value_objects.task_history import TaskAction
from c_application.dtos.task_dtos import (
    CancelTaskInputDTO,
    CreateTaskInputDTO,
    GetTaskRequest,
    ListTasksRequest,
    TaskByUserRequest,
    TaskOutputDTO,
    UpdateTaskInputDTO,
)
from c_application.handlers.task_handlers.follow_blockers_handler import (
    FollowBlockersHandler,
)
from c_application.use_cases import (
    CancelTaskUseCase,
    CompleteTaskUseCase,
    CreateTaskUseCase,
    DeleteTaskUseCase,
    GetTaskUseCase,
    ListTasksUseCase,
    ReopenTaskUseCase,
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
    created = User.create(username="ana", email="ana@test.com")
    await fake_uow_factory().users.add(created)
    return created


async def _add(
    deps: UseCaseDeps, user: User, title: str, **kw: object
) -> TaskOutputDTO:
    return await CreateTaskUseCase(**deps).execute(
        CreateTaskInputDTO(user_id=str(user.id), title=title, **kw)  # type: ignore[arg-type]
    )


async def _edit(
    deps: UseCaseDeps, user: User, task: TaskOutputDTO, **kw: object
) -> TaskOutputDTO:
    return await UpdateTaskUseCase(**deps).execute(
        UpdateTaskInputDTO(task_id_prefix=task.id[:8], user_id=str(user.id), **kw)  # type: ignore[arg-type]
    )


async def _show(deps: UseCaseDeps, user: User, task: TaskOutputDTO) -> TaskOutputDTO:
    return await GetTaskUseCase(**deps).execute(
        GetTaskRequest(task_id_prefix=task.id[:8], user_id=str(user.id))
    )


def _by(user: User, task: TaskOutputDTO) -> TaskByUserRequest:
    return TaskByUserRequest(task_id_prefix=task.id[:8], user_id=str(user.id))


async def _entity(uow_factory: FakeUowFactory, task: TaskOutputDTO) -> Task:
    async with uow_factory() as uow:
        found = await uow.tasks.get_by_id(TaskId.from_string(task.id))
    assert found is not None
    return found


async def _follow(
    uow_factory: FakeUowFactory, user: User, event_type: type, task: TaskOutputDTO
) -> None:
    """What the bus does after the change (the fake bus runs no handlers)."""
    kwargs: dict[str, object] = {
        "task_id": TaskId.from_string(task.id),
        "user_id": user.id,
    }
    if event_type is TaskCompletedEvent:
        from b_domain.value_objects.enums import EnergyLevel, TaskComplexity

        kwargs |= {
            "estimated_minutes": 30,
            "actual_minutes": 0,
            "energy_level_used": EnergyLevel.BALANCED,
            "task_complexity": TaskComplexity.MEDIUM,
        }
    await FollowBlockersHandler(uow_factory(), FakeClock()).handle(event_type(**kwargs))


# ----------------------------------------------------------------- parents


async def test_a_task_moves_under_a_parent_and_out(
    use_case_context: UseCaseDeps, user: User
) -> None:
    house = await _add(use_case_context, user, "Move house")
    books = await _add(use_case_context, user, "Pack the books")

    moved = await _edit(use_case_context, user, books, parent_id=house.id[:6])
    assert moved.parent_id == house.id
    assert moved.parent is not None and moved.parent.title == "Move house"

    shown = await _show(use_case_context, user, house)
    assert [s.title for s in shown.subtasks] == ["Pack the books"]
    assert shown.open_subtasks == 1 and shown.all_subtasks == 1

    alone = await _edit(use_case_context, user, books, remove_parent=True)
    assert alone.parent_id is None and alone.parent is None


async def test_subtasks_are_one_level_and_never_loop(
    use_case_context: UseCaseDeps, user: User
) -> None:
    house = await _add(use_case_context, user, "Move house")
    books = await _add(use_case_context, user, "Pack the books", parent_id=house.id)
    trip = await _add(use_case_context, user, "Trip")

    with pytest.raises(ValidationException, match="its own parent"):
        await _edit(use_case_context, user, house, parent_id=house.id)
    with pytest.raises(ValidationException, match="its own subtask"):
        await _edit(use_case_context, user, house, parent_id=books.id)
    # A subtask has no subtasks; a parent does not become one
    with pytest.raises(ValidationException, match="no subtasks of its own"):
        await _add(use_case_context, user, "Buy a box", parent_id=books.id)
    with pytest.raises(ValidationException, match="has subtasks"):
        await _edit(use_case_context, user, house, parent_id=trip.id)
    with pytest.raises(ValidationException, match="not both"):
        await _edit(
            use_case_context, user, books, parent_id=trip.id, remove_parent=True
        )


async def test_the_history_records_the_parent(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    house = await _add(use_case_context, user, "Move house")
    books = await _add(use_case_context, user, "Pack the books")
    await _edit(use_case_context, user, books, parent_id=house.id)

    async with fake_uow_factory() as uow:
        [edit] = [
            e
            for e in await uow.task_history.recent(user.id)
            if e.action == TaskAction.EDITED
        ]
    assert [(c.field, c.before, c.after) for c in edit.changes] == [
        ("parent", None, "Move house")
    ]


async def test_a_list_carries_each_parents_title(
    use_case_context: UseCaseDeps, user: User
) -> None:
    house = await _add(use_case_context, user, "Move house")
    await _add(use_case_context, user, "Pack the books", parent_id=house.id)

    listed = await ListTasksUseCase(**use_case_context).execute(
        ListTasksRequest(user_id=str(user.id))
    )
    by_title = {t.title: t for t in listed.tasks}
    assert by_title["Pack the books"].parent_title == "Move house"
    assert by_title["Move house"].parent_title is None


# ------------------------------------------------------------ dependencies


async def test_dependencies_are_added_and_removed(
    use_case_context: UseCaseDeps, user: User
) -> None:
    before = await _add(use_case_context, user, "Before")
    after = await _add(use_case_context, user, "After")

    waiting = await _edit(
        use_case_context, user, after, add_dependencies=[before.id[:6]]
    )
    assert waiting.is_blocked
    assert [w.title for w in waiting.waits_on] == ["Before"]
    assert [b.title for b in (await _show(use_case_context, user, before)).blocks] == [
        "After"
    ]

    free = await _edit(
        use_case_context, user, after, remove_dependencies=[before.id[:6]]
    )
    assert not free.is_blocked and free.waits_on == []


async def test_a_dependency_loop_is_refused(
    use_case_context: UseCaseDeps, user: User
) -> None:
    a = await _add(use_case_context, user, "Task A")
    b = await _add(use_case_context, user, "Task B", depends_on={a.id})
    c = await _add(use_case_context, user, "Task C", depends_on={b.id})

    with pytest.raises(ValidationException, match="depend on itself"):
        await _edit(use_case_context, user, a, add_dependencies=[a.id])
    with pytest.raises(ValidationException, match="wait on each other"):
        await _edit(use_case_context, user, a, add_dependencies=[c.id])
    with pytest.raises(ValidationException, match="does not depend"):
        await _edit(use_case_context, user, a, remove_dependencies=[b.id[:6]])


async def test_a_done_dependency_is_kept_and_holds_again_if_reopened(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    before = await _add(use_case_context, user, "Before")
    after = await _add(use_case_context, user, "After", depends_on={before.id})
    assert after.is_blocked

    await CompleteTaskUseCase(**use_case_context).execute(_by(user, before))
    await _follow(fake_uow_factory, user, TaskCompletedEvent, before)
    freed = await _show(use_case_context, user, after)
    assert not freed.is_blocked
    assert [(w.title, w.status) for w in freed.waits_on] == [("Before", "done")]

    await ReopenTaskUseCase(**use_case_context).execute(_by(user, before))
    await _follow(fake_uow_factory, user, TaskReopenedEvent, before)
    assert (await _show(use_case_context, user, after)).is_blocked


async def test_a_task_depending_on_a_done_one_is_born_free(
    use_case_context: UseCaseDeps, user: User
) -> None:
    before = await _add(use_case_context, user, "Before")
    await CompleteTaskUseCase(**use_case_context).execute(_by(user, before))

    after = await _add(use_case_context, user, "After", depends_on={before.id})

    assert not after.is_blocked
    assert [w.title for w in after.waits_on] == ["Before"]


async def test_undoing_a_dependency_edit_brings_the_old_ones_back(
    use_case_context: UseCaseDeps, user: User
) -> None:
    before = await _add(use_case_context, user, "Before")
    after = await _add(use_case_context, user, "After", depends_on={before.id})
    await _edit(use_case_context, user, after, remove_dependencies=[before.id[:6]])

    await UndoUseCase(**use_case_context).execute(UndoRequest(user_id=str(user.id)))

    back = await _show(use_case_context, user, after)
    assert [w.title for w in back.waits_on] == ["Before"] and back.is_blocked


# --------------------------------------------------- closing and deleting


async def test_completing_a_parent_completes_its_open_subtasks(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    house = await _add(use_case_context, user, "Move house")
    books = await _add(use_case_context, user, "Pack the books", parent_id=house.id)
    keys = await _add(use_case_context, user, "Get the keys", parent_id=house.id)

    assert (await _show(use_case_context, user, house)).open_subtasks == 2

    done = await CompleteTaskUseCase(**use_case_context).execute(_by(user, house))

    # Every one, at the parent's time
    assert done.subtasks_done == 2
    parent = await _entity(fake_uow_factory, house)
    for sub in (books, keys):
        found = await _entity(fake_uow_factory, sub)
        assert found.status == TaskStatus.DONE
        assert found.completed_at == parent.completed_at
    # One undo: the parent and the subtasks it closed
    preview = await UndoPreviewUseCase(**use_case_context).execute(
        UndoRequest(user_id=str(user.id))
    )
    assert sorted(preview.along) == ["Get the keys", "Pack the books"]
    assert preview.also == []
    await UndoUseCase(**use_case_context).execute(
        UndoRequest(user_id=str(user.id), entry_id=preview.entry_id)
    )
    assert (await _entity(fake_uow_factory, books)).status == TaskStatus.PENDING
    assert (await _entity(fake_uow_factory, keys)).status == TaskStatus.PENDING
    assert (await _show(use_case_context, user, house)).open_subtasks == 2


async def test_a_parent_is_not_done_while_an_open_subtask_waits(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    house = await _add(use_case_context, user, "Move house")
    books = await _add(use_case_context, user, "Pack the books", parent_id=house.id)
    keys = await _add(use_case_context, user, "Get the keys", parent_id=house.id)
    paint = await _add(
        use_case_context, user, "Paint", parent_id=house.id, depends_on={keys.id}
    )
    assert paint.is_blocked

    # A dependency is never ignored: nothing changes, and it says what holds
    with pytest.raises(
        InvalidStateTransition,
        match="'Move house' cannot be done: its subtask 'Paint' is waiting on "
        "'Get the keys'",
    ):
        await CompleteTaskUseCase(**use_case_context).execute(_by(user, house))
    for task in (house, books, keys):
        assert (await _entity(fake_uow_factory, task)).status == TaskStatus.PENDING
    assert (await _entity(fake_uow_factory, paint)).status == TaskStatus.BLOCKED

    # The waiting task alone is refused too, naming what it waits on
    with pytest.raises(InvalidStateTransition, match="'Paint' is waiting on 'Get"):
        await CompleteTaskUseCase(**use_case_context).execute(_by(user, paint))

    # Sorted out: the blocker done frees it, and then the parent goes
    await CompleteTaskUseCase(**use_case_context).execute(_by(user, keys))
    await _follow(fake_uow_factory, user, TaskCompletedEvent, keys)
    done = await CompleteTaskUseCase(**use_case_context).execute(_by(user, house))
    assert done.subtasks_done == 2


async def test_a_waiting_subtask_that_is_deleted_no_longer_holds_its_parent(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    house = await _add(use_case_context, user, "Move house")
    keys = await _add(use_case_context, user, "Get the keys", parent_id=house.id)
    paint = await _add(
        use_case_context, user, "Paint", parent_id=house.id, depends_on={keys.id}
    )
    with pytest.raises(InvalidStateTransition):
        await CompleteTaskUseCase(**use_case_context).execute(_by(user, house))

    await DeleteTaskUseCase(**use_case_context).execute(
        DeleteTaskInputDTO(task_id_prefix=paint.id[:8], user_id=str(user.id))
    )
    done = await CompleteTaskUseCase(**use_case_context).execute(_by(user, house))
    assert done.subtasks_done == 1


async def test_reopening_a_parent_brings_back_what_it_closed_along(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    house = await _add(use_case_context, user, "Move house")
    books = await _add(use_case_context, user, "Pack the books", parent_id=house.id)
    boxes = await _add(use_case_context, user, "Buy boxes", parent_id=house.id)
    keys = await _add(use_case_context, user, "Get the keys", parent_id=house.id)
    # One closed before the parent, another thrown away on its own
    await CompleteTaskUseCase(**use_case_context).execute(_by(user, boxes))
    await CancelTaskUseCase(**use_case_context).execute(
        CancelTaskInputDTO(task_id_prefix=keys.id[:8], user_id=str(user.id))
    )
    await CompleteTaskUseCase(**use_case_context).execute(_by(user, house))
    assert (await _entity(fake_uow_factory, books)).status == TaskStatus.DONE

    # The card says how many come back
    assert (await _show(use_case_context, user, house)).reopens_with == 1

    reopened = await ReopenTaskUseCase(**use_case_context).execute(_by(user, house))

    assert reopened.subtasks_reopened == 1
    assert (await _entity(fake_uow_factory, house)).status == TaskStatus.REOPENED
    assert (await _entity(fake_uow_factory, books)).status == TaskStatus.REOPENED
    # What was closed before stays closed
    assert (await _entity(fake_uow_factory, boxes)).status == TaskStatus.DONE
    assert (await _entity(fake_uow_factory, keys)).status == TaskStatus.CANCELLED

    # One undo takes it all back
    await UndoUseCase(**use_case_context).execute(UndoRequest(user_id=str(user.id)))
    assert (await _entity(fake_uow_factory, house)).status == TaskStatus.DONE
    assert (await _entity(fake_uow_factory, books)).status == TaskStatus.DONE


async def test_reopening_a_subtask_does_not_reopen_its_siblings(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    house = await _add(use_case_context, user, "Move house")
    books = await _add(use_case_context, user, "Pack the books", parent_id=house.id)
    boxes = await _add(use_case_context, user, "Buy boxes", parent_id=house.id)
    await CompleteTaskUseCase(**use_case_context).execute(_by(user, house))

    reopened = await ReopenTaskUseCase(**use_case_context).execute(_by(user, books))

    assert reopened.parent_reopened == "Move house"
    assert reopened.subtasks_reopened == 0
    assert (await _entity(fake_uow_factory, boxes)).status == TaskStatus.DONE


async def test_a_deleted_blocker_is_not_shown_until_it_comes_back(
    use_case_context: UseCaseDeps, user: User
) -> None:
    keys = await _add(use_case_context, user, "Get the keys")
    use = await _add(use_case_context, user, "Use the keys", depends_on={keys.id})
    assert [t.title for t in (await _show(use_case_context, user, use)).waits_on] == [
        "Get the keys"
    ]

    await DeleteTaskUseCase(**use_case_context).execute(
        DeleteTaskInputDTO(task_id_prefix=keys.id[:8], user_id=str(user.id))
    )
    assert (await _show(use_case_context, user, use)).waits_on == []

    await RestoreTaskUseCase(**use_case_context).execute(_by(user, keys))
    assert [t.title for t in (await _show(use_case_context, user, use)).waits_on] == [
        "Get the keys"
    ]


async def test_deleting_a_parent_takes_its_subtasks_and_restore_brings_them(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    house = await _add(use_case_context, user, "Move house")
    await _add(use_case_context, user, "Pack the books", parent_id=house.id)
    box = await _add(use_case_context, user, "Buy a box", parent_id=house.id)

    gone = await DeleteTaskUseCase(**use_case_context).execute(
        DeleteTaskInputDTO(task_id_prefix=house.id[:8], user_id=str(user.id))
    )
    assert gone.subtasks_deleted == 2
    assert (await _entity(fake_uow_factory, box)).deleted_at is not None

    back = await RestoreTaskUseCase(**use_case_context).execute(_by(user, house))
    assert back.subtasks_restored == 2
    assert (await _entity(fake_uow_factory, box)).deleted_at is None


async def test_undoing_a_parents_delete_brings_its_subtasks(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    house = await _add(use_case_context, user, "Move house")
    books = await _add(use_case_context, user, "Pack the books", parent_id=house.id)
    await DeleteTaskUseCase(**use_case_context).execute(
        DeleteTaskInputDTO(task_id_prefix=house.id[:8], user_id=str(user.id))
    )

    await UndoUseCase(**use_case_context).execute(UndoRequest(user_id=str(user.id)))

    assert (await _entity(fake_uow_factory, house)).deleted_at is None
    assert (await _entity(fake_uow_factory, books)).deleted_at is None


async def test_the_entity_refuses_itself_as_parent_or_dependency() -> None:
    from b_domain.value_objects import Title, UserId

    now = datetime(2026, 1, 1, 9, 0)
    task = Task.create(now=now, user_id=UserId(), title=Title("Alone"))
    with pytest.raises(ValidationException):
        task.move_under(now, task.id)
    with pytest.raises(ValidationException):
        task.set_dependencies(now, {task.id}, waiting=True)
