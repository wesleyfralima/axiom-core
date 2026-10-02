"""What acts on several tasks at once (product Backlog 02, 2026-10-02): one
undo per command typed, dependencies within a family, a parent ready once
its last subtask is done."""

from uuid import UUID, uuid4

import pytest

from a_core.exceptions import ValidationException
from b_domain.entities import User
from b_domain.value_objects import RecurrenceInterval, TaskStatus
from c_application.dtos.recurrence_dtos import RecurrenceInputDTO
from c_application.dtos.task_dtos import (
    CancelTaskInputDTO,
    CreateTaskInputDTO,
    GetTaskRequest,
    TaskByUserRequest,
    TaskOutputDTO,
    UpdateTaskInputDTO,
)
from c_application.use_cases import (
    CancelTaskUseCase,
    CompleteTaskUseCase,
    CreateTaskUseCase,
    DeleteTaskUseCase,
    GetTaskUseCase,
    UndoPreviewUseCase,
    UndoUseCase,
    UpdateTaskUseCase,
)
from c_application.use_cases.task.delete import DeleteTaskInputDTO
from c_application.use_cases.task.undo import UndoRequest
from tests.conftest import FakeClock, FakeUnitOfWork, FakeUowFactory, UseCaseDeps

pytestmark = [pytest.mark.asyncio, pytest.mark.uc]


@pytest.fixture
async def user(fake_uow_factory: FakeUowFactory) -> User:
    created = User.create(username="ana", email="ana@test.com")
    await fake_uow_factory().users.add(created)
    return created


def _command(
    factory: FakeUowFactory, clock: FakeClock, command: UUID | None = None
) -> UseCaseDeps:
    """Use case dependencies as one command typed: every unit of work
    carries the same command ID (the interface makes one per command)."""
    command_id: UUID = command or uuid4()

    def make(trigger_relay: bool = False) -> FakeUnitOfWork:
        uow = factory(trigger_relay)
        uow.command_id = command_id
        return uow

    return {"uow_factory": make, "clock": clock}


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


async def _status(deps: UseCaseDeps, user: User, task: TaskOutputDTO) -> str:
    shown = await GetTaskUseCase(**deps).execute(
        GetTaskRequest(task_id_prefix=task.id[:8], user_id=str(user.id))
    )
    return shown.status


def _by(user: User, task: TaskOutputDTO) -> TaskByUserRequest:
    return TaskByUserRequest(task_id_prefix=task.id[:8], user_id=str(user.id))


# ---------- One undo per command ----------


async def test_one_undo_takes_back_the_whole_command(
    use_case_context: UseCaseDeps,
    user: User,
    fake_uow_factory: FakeUowFactory,
    fake_clock: FakeClock,
) -> None:
    first = await _add(_command(fake_uow_factory, fake_clock), user, "First")
    tasks = [
        await _add(use_case_context, user, title) for title in ("Aaa", "Bbb", "Ccc")
    ]

    # `task cancel a b c`: one command, three changes
    cancel_abc = _command(fake_uow_factory, fake_clock)
    for task in tasks:
        await CancelTaskUseCase(**cancel_abc).execute(
            CancelTaskInputDTO(task_id_prefix=task.id[:8], user_id=str(user.id))
        )

    undo = _command(fake_uow_factory, fake_clock)
    preview = await UndoPreviewUseCase(**undo).execute(
        UndoRequest(user_id=str(user.id))
    )
    assert preview.title == "Ccc"
    assert [m.title for m in preview.more] == ["Bbb", "Aaa"]
    assert [m.entry.action for m in preview.more] == ["cancelled", "cancelled"]

    done = await UndoUseCase(**undo).execute(
        UndoRequest(user_id=str(user.id), entry_id=preview.entry_id)
    )

    assert (done.title, [m.title for m in done.more]) == ("Ccc", ["Bbb", "Aaa"])
    for task in tasks:
        assert await _status(use_case_context, user, task) == "pending"
    # The next undo goes further back: the tasks created one by one (no
    # command recorded), then "First"
    again = await UndoPreviewUseCase(**use_case_context).execute(
        UndoRequest(user_id=str(user.id))
    )
    assert (again.title, again.more) == ("Ccc", [])
    for _ in tasks:
        await UndoUseCase(**use_case_context).execute(UndoRequest(user_id=str(user.id)))
    last = await UndoPreviewUseCase(**use_case_context).execute(
        UndoRequest(user_id=str(user.id))
    )
    assert last.task_id == first.id


async def test_a_command_with_a_purged_task_is_not_undone_in_part(
    user: User, fake_uow_factory: FakeUowFactory, fake_clock: FakeClock
) -> None:
    command = _command(fake_uow_factory, fake_clock)
    kept = await _add(command, user, "Kept")
    gone = await _add(command, user, "Gone")
    async with fake_uow_factory() as uow:
        del uow.tasks.tasks[gone.id]

    preview = await UndoPreviewUseCase(**command).execute(
        UndoRequest(user_id=str(user.id))
    )
    assert preview.blocked is not None
    with pytest.raises(Exception, match="purged"):
        await UndoUseCase(**command).execute(UndoRequest(user_id=str(user.id)))
    assert await _status(command, user, kept) == "pending"


# ---------- Dependencies within a family ----------


async def test_siblings_may_wait_on_each_other(
    use_case_context: UseCaseDeps, user: User
) -> None:
    house = await _add(use_case_context, user, "Clean the house")
    broom = await _add(use_case_context, user, "Buy a broom", parent_id=house.id)
    sweep = await _add(use_case_context, user, "Sweep the floor", parent_id=house.id)

    edited = await _edit(use_case_context, user, sweep, add_dependencies=[broom.id])

    assert edited.is_blocked


@pytest.mark.parametrize("waiting_is_the_subtask", [True, False])
async def test_a_subtask_and_a_task_outside_its_family_never_wait_on_each_other(
    use_case_context: UseCaseDeps, user: User, waiting_is_the_subtask: bool
) -> None:
    house = await _add(use_case_context, user, "Clean the house")
    broom = await _add(use_case_context, user, "Buy a broom", parent_id=house.id)
    barbecue = await _add(use_case_context, user, "Barbecue with friends")
    waiting, blocker = (
        (broom, barbecue) if waiting_is_the_subtask else (barbecue, broom)
    )

    with pytest.raises(ValidationException, match="subtask"):
        await _edit(use_case_context, user, waiting, add_dependencies=[blocker.id])
    with pytest.raises(ValidationException, match="subtask"):
        await _add(
            use_case_context,
            user,
            "Newcomer",
            parent_id=house.id if waiting_is_the_subtask else None,
            depends_on={barbecue.id if waiting_is_the_subtask else broom.id},
        )


async def test_a_parent_and_its_own_subtask_never_wait_on_each_other(
    use_case_context: UseCaseDeps, user: User
) -> None:
    house = await _add(use_case_context, user, "Clean the house")
    broom = await _add(use_case_context, user, "Buy a broom", parent_id=house.id)

    with pytest.raises(ValidationException, match="only its siblings"):
        await _edit(use_case_context, user, house, add_dependencies=[broom.id])
    with pytest.raises(ValidationException, match="only wait on its siblings"):
        await _edit(use_case_context, user, broom, add_dependencies=[house.id])


@pytest.mark.parametrize("moved_is_the_blocker", [True, False])
async def test_a_task_linked_outside_cannot_become_a_subtask(
    use_case_context: UseCaseDeps, user: User, moved_is_the_blocker: bool
) -> None:
    house = await _add(use_case_context, user, "Clean the house")
    broom = await _add(use_case_context, user, "Buy a broom")
    barbecue = await _add(
        use_case_context, user, "Barbecue with friends", depends_on={broom.id}
    )
    # The one holding a task outside the family it would join, or the one
    # waiting on it
    moved = broom if moved_is_the_blocker else barbecue

    with pytest.raises(ValidationException, match="remove the dependency first"):
        await _edit(use_case_context, user, moved, parent_id=house.id)


async def test_removing_the_dependency_in_the_same_edit_is_enough(
    use_case_context: UseCaseDeps, user: User
) -> None:
    house = await _add(use_case_context, user, "Clean the house")
    broom = await _add(use_case_context, user, "Buy a broom")
    barbecue = await _add(
        use_case_context, user, "Barbecue with friends", depends_on={broom.id}
    )

    moved = await _edit(
        use_case_context,
        user,
        barbecue,
        parent_id=house.id,
        remove_dependencies=[broom.id[:8]],
    )

    assert moved.parent_id == house.id


async def test_a_subtask_linked_to_its_siblings_cannot_leave_the_family(
    use_case_context: UseCaseDeps, user: User
) -> None:
    house = await _add(use_case_context, user, "Clean the house")
    broom = await _add(use_case_context, user, "Buy a broom", parent_id=house.id)
    await _add(
        use_case_context,
        user,
        "Sweep the floor",
        parent_id=house.id,
        depends_on={broom.id},
    )

    with pytest.raises(ValidationException, match="remove the dependency first"):
        await _edit(use_case_context, user, broom, remove_parent=True)


# ---------- The parent once its last subtask is done ----------


async def test_the_last_open_subtask_done_says_its_parent_is_ready(
    use_case_context: UseCaseDeps, user: User
) -> None:
    house = await _add(use_case_context, user, "Clean the house")
    broom = await _add(use_case_context, user, "Buy a broom", parent_id=house.id)
    sweep = await _add(use_case_context, user, "Sweep the floor", parent_id=house.id)
    dust = await _add(use_case_context, user, "Dust the shelves", parent_id=house.id)
    await CancelTaskUseCase(**use_case_context).execute(
        CancelTaskInputDTO(task_id_prefix=dust.id[:8], user_id=str(user.id))
    )
    complete = CompleteTaskUseCase(**use_case_context)

    first = await complete.execute(_by(user, broom))
    assert first.parent_ready is None  # "Sweep the floor" is still open

    last = await complete.execute(_by(user, sweep))
    assert last.parent_ready is not None
    assert (last.parent_ready.id, last.parent_ready.status) == (house.id, "pending")
    # Nothing done on its own: the parent stays open until asked
    assert await _status(use_case_context, user, house) == TaskStatus.PENDING.value


async def test_a_task_of_its_own_has_no_parent_to_be_ready(
    use_case_context: UseCaseDeps, user: User
) -> None:
    alone = await _add(use_case_context, user, "Alone")
    assert (
        await CompleteTaskUseCase(**use_case_context).execute(_by(user, alone))
    ).parent_ready is None


# ---------- Deleting a recurring task ----------


async def test_deleting_a_recurring_task_says_the_series_ends(
    use_case_context: UseCaseDeps, user: User
) -> None:
    gym = await _add(
        use_case_context,
        user,
        "Gym",
        recurrence=RecurrenceInputDTO(
            frequency=RecurrenceInterval.DAILY, start_date="2026-01-06 07:00"
        ),
    )
    once = await _add(use_case_context, user, "Once")
    delete = DeleteTaskUseCase(**use_case_context)

    gone = await delete.execute(
        DeleteTaskInputDTO(task_id_prefix=gym.id[:8], user_id=str(user.id))
    )
    assert gone.series_ended
    assert not (
        await delete.execute(
            DeleteTaskInputDTO(task_id_prefix=once.id[:8], user_id=str(user.id))
        )
    ).series_ended
