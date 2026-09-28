"""Subtasks: a parent's checklist, as tasks, never bigger than the parent."""

from datetime import UTC, datetime

import pytest

from a_core import UniqueId
from a_core.exceptions import InvalidStateTransition, ValidationException
from b_domain.entities import Task, User
from b_domain.entities.task import subtask_copy_id
from b_domain.events.task_events import TaskCompletedEvent
from b_domain.value_objects import TaskId, TaskStatus
from b_domain.value_objects.dates import DueDate
from b_domain.value_objects.enums import Priority, RecurrenceInterval
from b_domain.value_objects.task_history import TaskAction
from c_application.dtos.recurrence_dtos import RecurrenceInputDTO
from c_application.dtos.task_dtos import (
    AddSubtasksInputDTO,
    CancelTaskInputDTO,
    CreateTaskInputDTO,
    SubtasksAddedOutputDTO,
    TaskByUserRequest,
    TaskOutputDTO,
    UpdateTaskInputDTO,
)
from c_application.handlers.task_handlers.create_recurring_task_handler import (
    CreateRecurringTaskHandler,
)
from c_application.use_cases import (
    AddSubtasksUseCase,
    ArchiveTaskUseCase,
    CancelTaskUseCase,
    CompleteTaskUseCase,
    CreateTaskUseCase,
    DeleteTaskUseCase,
    ReopenTaskUseCase,
    UndoPreviewUseCase,
    UndoUseCase,
    UpdateTaskUseCase,
)
from c_application.use_cases.task.delete import DeleteTaskInputDTO
from c_application.use_cases.task.relations import minutes_text, shifted_due
from c_application.use_cases.task.undo import UndoRequest
from tests.conftest import FakeUowFactory, UseCaseDeps

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


async def _add_to(
    deps: UseCaseDeps, user: User, parent: TaskOutputDTO, *titles: str, **kw: object
) -> SubtasksAddedOutputDTO:
    return await AddSubtasksUseCase(**deps).execute(
        AddSubtasksInputDTO(
            user_id=str(user.id),
            parent_id=parent.id[:8],
            titles=list(titles),
            **kw,  # type: ignore[arg-type]
        )
    )


async def _edit(
    deps: UseCaseDeps, user: User, task: TaskOutputDTO, **kw: object
) -> TaskOutputDTO:
    return await UpdateTaskUseCase(**deps).execute(
        UpdateTaskInputDTO(task_id_prefix=task.id[:8], user_id=str(user.id), **kw)  # type: ignore[arg-type]
    )


def _by(user: User, task: TaskOutputDTO) -> TaskByUserRequest:
    return TaskByUserRequest(task_id_prefix=task.id[:8], user_id=str(user.id))


async def _entity(uow_factory: FakeUowFactory, task: TaskOutputDTO | str) -> Task:
    ref: str = task if isinstance(task, str) else task.id
    async with uow_factory() as uow:
        found = await uow.tasks.get_by_id(TaskId.from_string(ref))
    assert found is not None
    return found


async def _undo(deps: UseCaseDeps, user: User) -> None:
    preview = await UndoPreviewUseCase(**deps).execute(
        UndoRequest(user_id=str(user.id))
    )
    await UndoUseCase(**deps).execute(
        UndoRequest(user_id=str(user.id), entry_id=preview.entry_id)
    )


def _due(task: TaskOutputDTO | Task) -> str | None:
    """A due date as the tests write it (wall-clock time)."""
    if isinstance(task, Task):
        return task.due_date.value.strftime("%Y-%m-%d %H:%M") if task.due_date else None
    return task.due_date.strftime("%Y-%m-%d %H:%M") if task.due_date else None


# ------------------------------------------------------------------ adding


async def test_subtasks_take_from_their_parent_what_they_are_not_given(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    trip = await _add(
        use_case_context,
        user,
        "Trip",
        due_date="2026-12-10 18:00",
        priority=3,
        estimated_minutes=30,
    )

    added = await _add_to(
        use_case_context, user, trip, "Book the car", "Pack", estimated_minutes=20
    )

    assert [s.title for s in added.subtasks] == ["Book the car", "Pack"]
    for sub in added.subtasks:
        assert sub.parent_id == trip.id
        assert _due(sub) == "2026-12-10 18:00"
        assert sub.priority == "HIGH"
    # 20 + 20 fit in the parent's 30 minutes no more: it grows to 40
    assert added.parent.estimated_minutes == 40
    assert added.notes == ["'Trip' now takes 40 min: its subtasks take that long."]
    assert [s.title for s in added.parent.subtasks] == ["Book the car", "Pack"]


async def test_a_subtask_is_due_no_later_and_no_higher_than_its_parent(
    use_case_context: UseCaseDeps, user: User
) -> None:
    trip = await _add(
        use_case_context, user, "Trip", due_date="2026-12-10 18:00", priority=2
    )

    with pytest.raises(ValidationException, match=r"is due 2026-12-10 18:00\."):
        await _add_to(use_case_context, user, trip, "Late", due_date="2026-12-11")
    with pytest.raises(ValidationException, match="no higher than its parent"):
        await _add_to(use_case_context, user, trip, "Urgent", priority=4)

    # Earlier and lower: fine
    added = await _add_to(
        use_case_context,
        user,
        trip,
        "Book the car",
        due_date="2026-11-20 09:00",
        priority=1,
    )
    [car] = added.subtasks
    assert _due(car) == "2026-11-20 09:00" and car.priority == "LOW"


async def test_a_parent_with_no_due_date_takes_any(
    use_case_context: UseCaseDeps, user: User
) -> None:
    someday = await _add(use_case_context, user, "Learn Rust")

    added = await _add_to(
        use_case_context, user, someday, "Read the book", due_date="2027-01-10"
    )
    assert added.subtasks[0].due_date is not None
    none = await _add_to(use_case_context, user, someday, "Do the exercises")
    assert none.subtasks[0].due_date is None


async def test_some_parents_take_no_subtasks(
    use_case_context: UseCaseDeps, user: User
) -> None:
    house = await _add(use_case_context, user, "Move house")
    [books] = (await _add_to(use_case_context, user, house, "Pack the books")).subtasks
    done = await _add(use_case_context, user, "Done already")
    await CompleteTaskUseCase(**use_case_context).execute(_by(user, done))

    with pytest.raises(ValidationException, match="no subtasks of its own"):
        await _add_to(use_case_context, user, books, "Buy a box")
    with pytest.raises(ValidationException, match="reopen it"):
        await _add_to(use_case_context, user, done, "More")
    with pytest.raises(ValidationException, match="at least one"):
        await _add_to(use_case_context, user, house, " ")
    with pytest.raises(ValidationException, match="does not repeat"):
        await _add(
            use_case_context,
            user,
            "Daily",
            parent_id=house.id,
            recurrence=RecurrenceInputDTO(frequency=RecurrenceInterval.DAILY),
        )


async def test_the_context_comes_from_the_parent(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    from b_domain.entities import Context

    home = Context.create(
        now=datetime(2026, 3, 5, tzinfo=UTC), user_id=user.id, name="Home"
    )
    async with fake_uow_factory() as uow:
        await uow.contexts.add(home)
    house = await _add(use_case_context, user, "Move house", context_id="Home")

    added = await _add_to(use_case_context, user, house, "Pack the books")

    assert added.subtasks[0].context_name == "Home"


async def test_one_undo_takes_back_everything_add_to_did(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    trip = await _add(use_case_context, user, "Trip", estimated_minutes=30)
    await _add_to(
        use_case_context, user, trip, "Book the car", "Pack", estimated_minutes=25
    )
    assert (await _entity(fake_uow_factory, trip)).estimated_duration_minutes == 50

    preview = await UndoPreviewUseCase(**use_case_context).execute(
        UndoRequest(user_id=str(user.id))
    )
    assert preview.also == ["Pack"] and preview.along == ["Trip"]
    await _undo(use_case_context, user)

    async with fake_uow_factory() as uow:
        assert await uow.tasks.get_subtasks(TaskId.from_string(trip.id)) == []
    assert (await _entity(fake_uow_factory, trip)).estimated_duration_minutes == 30


# ----------------------------------------------------------- editing a subtask


async def test_a_subtasks_edit_is_refused_beyond_its_parent(
    use_case_context: UseCaseDeps, user: User
) -> None:
    trip = await _add(
        use_case_context, user, "Trip", due_date="2026-12-10 18:00", priority=2
    )
    [car] = (await _add_to(use_case_context, user, trip, "Book the car")).subtasks

    with pytest.raises(ValidationException, match="due no later"):
        await _edit(use_case_context, user, car, due_date="2026-12-11")
    with pytest.raises(ValidationException, match="due no later"):
        await _edit(use_case_context, user, car, remove_due_date=True)
    with pytest.raises(ValidationException, match="no higher"):
        await _edit(use_case_context, user, car, priority="high")
    with pytest.raises(ValidationException, match="does not repeat"):
        await _edit(
            use_case_context,
            user,
            car,
            recurrence=RecurrenceInputDTO(frequency=RecurrenceInterval.DAILY),
        )

    earlier = await _edit(use_case_context, user, car, due_date="2026-11-20 09:00")
    assert _due(earlier) == "2026-11-20 09:00"


async def test_a_longer_subtask_raises_its_parent_and_undo_lowers_it(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    trip = await _add(use_case_context, user, "Trip", estimated_minutes=60)
    [car, _] = (
        await _add_to(
            use_case_context, user, trip, "Book the car", "Pack", estimated_minutes=20
        )
    ).subtasks
    assert (await _entity(fake_uow_factory, trip)).estimated_duration_minutes == 60

    edited = await _edit(use_case_context, user, car, estimated_minutes=50)

    assert edited.notes == ["'Trip' now takes 1h10: its subtasks take that long."]
    assert (await _entity(fake_uow_factory, trip)).estimated_duration_minutes == 70

    await _undo(use_case_context, user)
    assert (await _entity(fake_uow_factory, trip)).estimated_duration_minutes == 60
    assert (await _entity(fake_uow_factory, car)).estimated_duration_minutes == 20


async def test_a_parent_takes_no_less_than_its_subtasks_together(
    use_case_context: UseCaseDeps, user: User
) -> None:
    trip = await _add(use_case_context, user, "Trip", estimated_minutes=30)
    await _add_to(use_case_context, user, trip, "One", "Two", estimated_minutes=30)

    with pytest.raises(ValidationException, match="together: 1h"):
        await _edit(use_case_context, user, trip, estimated_minutes=45)
    assert (await _edit(use_case_context, user, trip, estimated_minutes=90)).notes == []


async def test_removing_a_subtask_leaves_the_parents_estimate(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    trip = await _add(use_case_context, user, "Trip", estimated_minutes=30)
    [a, _] = (
        await _add_to(use_case_context, user, trip, "One", "Two", estimated_minutes=30)
    ).subtasks

    await _edit(use_case_context, user, a, remove_parent=True)

    assert (await _entity(fake_uow_factory, trip)).estimated_duration_minutes == 60


# ------------------------------------------------------------ the parent rules


async def test_a_parents_new_due_date_brings_its_subtasks_along(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    trip = await _add(use_case_context, user, "Trip", due_date="2026-12-10 18:00")
    [pack, car, hotel] = (
        await _add_to(use_case_context, user, trip, "Pack", "Book the car", "Hotel")
    ).subtasks
    await _edit(use_case_context, user, car, due_date="2026-11-20 09:00")
    await _edit(use_case_context, user, hotel, due_date="2026-12-01 09:00")

    # Later: the one due with it follows; the others stay
    later = await _edit(use_case_context, user, trip, due_date="2026-12-20 18:00")
    assert later.notes == ["'Pack': due date changed with its parent."]
    assert _due(await _entity(fake_uow_factory, pack)) == "2026-12-20 18:00"
    assert _due(await _entity(fake_uow_factory, car)) == "2026-11-20 09:00"

    # Earlier: the ones that would be later come to it; earlier ones stay
    earlier = await _edit(use_case_context, user, trip, due_date="2026-11-25 18:00")
    assert sorted(earlier.notes) == [
        "'Hotel': due date changed with its parent.",
        "'Pack': due date changed with its parent.",
    ]
    assert _due(await _entity(fake_uow_factory, hotel)) == "2026-11-25 18:00"
    assert _due(await _entity(fake_uow_factory, pack)) == "2026-11-25 18:00"
    assert _due(await _entity(fake_uow_factory, car)) == "2026-11-20 09:00"

    # One undo brings the parent and its subtasks back
    await _undo(use_case_context, user)
    assert _due(await _entity(fake_uow_factory, trip)) == "2026-12-20 18:00"
    assert _due(await _entity(fake_uow_factory, hotel)) == "2026-12-01 09:00"
    assert _due(await _entity(fake_uow_factory, pack)) == "2026-12-20 18:00"


async def test_a_parents_due_date_given_or_removed(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    trip = await _add(use_case_context, user, "Trip")
    [pack, car] = (
        await _add_to(use_case_context, user, trip, "Pack", "Book the car")
    ).subtasks
    await _edit(use_case_context, user, car, due_date="2026-12-20 09:00")

    # Given: the one with no date takes it; the later one comes to it
    await _edit(use_case_context, user, trip, due_date="2026-12-10 18:00")
    assert _due(await _entity(fake_uow_factory, pack)) == "2026-12-10 18:00"
    assert _due(await _entity(fake_uow_factory, car)) == "2026-12-10 18:00"

    await _edit(use_case_context, user, car, due_date="2026-11-20 09:00")
    # Removed: the one due with it loses it too; one of its own keeps it
    await _edit(use_case_context, user, trip, remove_due_date=True)
    assert (await _entity(fake_uow_factory, pack)).due_date is None
    assert _due(await _entity(fake_uow_factory, car)) == "2026-11-20 09:00"


async def test_lowering_a_parents_priority_lowers_the_higher_subtasks(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    trip = await _add(use_case_context, user, "Trip", priority=4)
    [urgent, low] = (await _add_to(use_case_context, user, trip, "Urgent")).subtasks + (
        await _add_to(use_case_context, user, trip, "Later", priority=1)
    ).subtasks

    edited = await _edit(use_case_context, user, trip, priority="medium")

    assert edited.notes == ["'Urgent': priority changed with its parent."]
    assert (await _entity(fake_uow_factory, urgent)).priority == Priority.MEDIUM
    assert (await _entity(fake_uow_factory, low)).priority == Priority.LOW


async def test_a_closed_subtask_stays_as_it_is(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    trip = await _add(use_case_context, user, "Trip", priority=4)
    [done] = (await _add_to(use_case_context, user, trip, "Done")).subtasks
    await CompleteTaskUseCase(**use_case_context).execute(_by(user, done))

    await _edit(use_case_context, user, trip, priority="low")

    assert (await _entity(fake_uow_factory, done)).priority == Priority.CRITICAL


# ---------------------------------------------------------- moving under one


async def test_a_task_moved_under_a_parent_is_brought_within_it(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    trip = await _add(
        use_case_context,
        user,
        "Trip",
        due_date="2026-12-10 18:00",
        priority=2,
        estimated_minutes=30,
    )
    late = await _add(
        use_case_context,
        user,
        "Book the car",
        due_date="2026-12-20",
        priority=4,
        estimated_minutes=45,
    )
    loose = await _add(use_case_context, user, "Pack", estimated_minutes=30)

    moved = await _edit(use_case_context, user, late, parent_id=trip.id[:8])

    assert _due(moved) == "2026-12-10 18:00" and moved.priority == "MEDIUM"
    assert moved.notes == [
        "'Book the car' moved to its parent's due date.",
        "'Book the car' priority lowered to medium, its parent's.",
        "'Trip' now takes 45 min: its subtasks take that long.",
    ]
    assert [minutes_text(m) for m in (45, 60, 170)] == ["45 min", "1h", "2h50"]
    no_date = await _edit(use_case_context, user, loose, parent_id=trip.id[:8])
    assert _due(no_date) == "2026-12-10 18:00"
    assert no_date.notes[0] == "'Pack' is now due with its parent."
    assert (await _entity(fake_uow_factory, trip)).estimated_duration_minutes == 75

    # Moved and asked beyond the parent at once: refused
    other = await _add(use_case_context, user, "Other")
    with pytest.raises(ValidationException, match="due no later"):
        await _edit(
            use_case_context, user, other, parent_id=trip.id, due_date="2026-12-31"
        )


async def test_a_recurring_task_does_not_become_a_subtask(
    use_case_context: UseCaseDeps, user: User
) -> None:
    trip = await _add(use_case_context, user, "Trip")
    gym = await _add(
        use_case_context,
        user,
        "Gym",
        recurrence=RecurrenceInputDTO(frequency=RecurrenceInterval.DAILY),
    )

    with pytest.raises(ValidationException, match="stop repeating it first"):
        await _edit(use_case_context, user, gym, parent_id=trip.id)


# ------------------------------------------------------------------ states


async def test_cancelling_a_parent_cancels_its_open_subtasks(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    trip = await _add(use_case_context, user, "Trip")
    [pack, car] = (
        await _add_to(use_case_context, user, trip, "Pack", "Book the car")
    ).subtasks
    await CompleteTaskUseCase(**use_case_context).execute(_by(user, car))

    cancelled = await CancelTaskUseCase(**use_case_context).execute(
        CancelTaskInputDTO(task_id_prefix=trip.id[:8], user_id=str(user.id))
    )

    assert cancelled.subtasks_along == 1
    assert (await _entity(fake_uow_factory, pack)).status == TaskStatus.CANCELLED
    assert (await _entity(fake_uow_factory, car)).status == TaskStatus.DONE
    await _undo(use_case_context, user)
    assert (await _entity(fake_uow_factory, pack)).status == TaskStatus.PENDING


async def test_archiving_a_parent_archives_its_subtasks(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    trip = await _add(use_case_context, user, "Trip")
    [pack] = (await _add_to(use_case_context, user, trip, "Pack")).subtasks
    await CompleteTaskUseCase(**use_case_context).execute(_by(user, trip))

    archived = await ArchiveTaskUseCase(**use_case_context).execute(_by(user, trip))

    assert archived.subtasks_along == 1
    assert (await _entity(fake_uow_factory, pack)).status == TaskStatus.ARCHIVED
    await _undo(use_case_context, user)
    assert (await _entity(fake_uow_factory, pack)).status == TaskStatus.DONE


async def test_reopening_a_subtask_reopens_its_closed_parent(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    trip = await _add(use_case_context, user, "Trip")
    [pack] = (await _add_to(use_case_context, user, trip, "Pack")).subtasks
    await CompleteTaskUseCase(**use_case_context).execute(_by(user, trip))

    reopened = await ReopenTaskUseCase(**use_case_context).execute(_by(user, pack))

    assert reopened.parent_reopened == "Trip"
    assert (await _entity(fake_uow_factory, trip)).status == TaskStatus.REOPENED
    await _undo(use_case_context, user)
    assert (await _entity(fake_uow_factory, trip)).status == TaskStatus.DONE
    assert (await _entity(fake_uow_factory, pack)).status == TaskStatus.DONE

    await ArchiveTaskUseCase(**use_case_context).execute(_by(user, trip))
    with pytest.raises(InvalidStateTransition, match="archived"):
        await ReopenTaskUseCase(**use_case_context).execute(_by(user, pack))


async def test_reopening_a_subtask_of_an_open_parent_leaves_it(
    use_case_context: UseCaseDeps, user: User
) -> None:
    trip = await _add(use_case_context, user, "Trip")
    [pack] = (await _add_to(use_case_context, user, trip, "Pack")).subtasks
    await CompleteTaskUseCase(**use_case_context).execute(_by(user, pack))

    reopened = await ReopenTaskUseCase(**use_case_context).execute(_by(user, pack))

    assert reopened.parent_reopened is None


# ------------------------------------------------------------- recurrence


async def _complete_following(
    deps: UseCaseDeps, user: User, task: TaskOutputDTO, uow_factory: FakeUowFactory
) -> None:
    """Complete ``task``, then what the handler does after it (the fake bus
    runs no handlers)."""
    await CompleteTaskUseCase(**deps).execute(_by(user, task))
    async with uow_factory() as uow:
        completion = next(
            e
            for e in await uow.task_history.recent(user.id)
            if e.action == TaskAction.COMPLETED and str(e.task_id) == task.id
        )
        done = await uow.tasks.get_by_id(TaskId.from_string(task.id))
    assert done is not None
    await CreateRecurringTaskHandler(uow_factory()).handle(
        TaskCompletedEvent(
            id=UniqueId(completion.entry_id),
            occurred_at=completion.occurred_at,
            task_id=done.id,
            user_id=user.id,
            estimated_minutes=30,
            actual_minutes=0,
            energy_level_used=done.required_energy_level,
            task_complexity=done.complexity,
        )
    )


async def test_a_recurring_parent_brings_its_subtasks_to_the_next_occurrence(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    bedtime = await _add(
        use_case_context,
        user,
        "Bedtime routine",
        recurrence=RecurrenceInputDTO(
            frequency=RecurrenceInterval.DAILY, start_date="2026-03-06 22:00"
        ),
    )
    [stretch, teeth, gone] = (
        await _add_to(
            use_case_context,
            user,
            bedtime,
            "Stretch",
            "Brush teeth",
            "Gone",
            estimated_minutes=10,
        )
    ).subtasks
    await _edit(use_case_context, user, stretch, due_date="2026-03-06 21:30")
    await DeleteTaskUseCase(**use_case_context).execute(
        DeleteTaskInputDTO(task_id_prefix=gone.id[:8], user_id=str(user.id))
    )

    await _complete_following(use_case_context, user, bedtime, fake_uow_factory)

    async with fake_uow_factory() as uow:
        [following] = [
            t
            for t in uow.tasks.tasks.values()
            if t.series_id is not None
            and str(t.series_id) == bedtime.id
            and t.status == TaskStatus.PENDING
        ]
        copies = await uow.tasks.get_subtasks(following.id)
    assert _due(following) == "2026-03-07 22:00"
    # The ones it has now, open again, each as far before it as it was
    assert [(c.title.value, _due(c), c.status) for c in copies] == [
        ("Stretch", "2026-03-07 21:30", TaskStatus.PENDING),
        ("Brush teeth", "2026-03-07 22:00", TaskStatus.PENDING),
    ]
    # The same row on every device
    assert copies[0].id == subtask_copy_id(following.id, TaskId.from_string(stretch.id))
    assert str(copies[1].id) == str(
        subtask_copy_id(following.id, TaskId.from_string(teeth.id))
    )

    # One undo of the completion takes them away with the next occurrence
    await _undo(use_case_context, user)
    async with fake_uow_factory() as uow:
        assert await uow.tasks.get_subtasks(following.id) == []


async def test_a_subtask_never_repeats_on_its_own(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    """One that repeated before the rule (made by hand here) stops."""
    house = await _add(use_case_context, user, "Move house")
    daily = await _add(
        use_case_context,
        user,
        "Water the plants",
        recurrence=RecurrenceInputDTO(
            frequency=RecurrenceInterval.DAILY, start_date="2026-03-06 08:00"
        ),
    )
    async with fake_uow_factory() as uow:
        plants = await uow.tasks.get_by_id(TaskId.from_string(daily.id))
        assert plants is not None
        plants.parent_id = TaskId.from_string(house.id)

    await _complete_following(use_case_context, user, daily, fake_uow_factory)

    async with fake_uow_factory() as uow:
        assert [
            t.title.value
            for t in uow.tasks.tasks.values()
            if t.status == TaskStatus.PENDING
        ] == ["Move house"]


async def test_a_subtasks_distance_to_its_parent_is_kept() -> None:
    parent = DueDate.fixed(datetime(2026, 3, 6, 22, tzinfo=UTC))
    after = DueDate.fixed(datetime(2026, 3, 7, 22, tzinfo=UTC))
    before = DueDate.fixed(datetime(2026, 3, 6, 21, 30, tzinfo=UTC))
    floating = DueDate.floating(datetime(2026, 3, 6, 18, 30), "America/Sao_Paulo")

    assert shifted_due(before, parent, after) == DueDate.fixed(
        datetime(2026, 3, 7, 21, 30, tzinfo=UTC)
    )
    assert shifted_due(None, parent, after) == after
    assert shifted_due(parent, parent, after) == after
    # Kinds apart: the instant, in the subtask's own kind
    moved = shifted_due(floating, parent, after)
    assert moved is not None and moved.is_floating
    assert moved.value == datetime(2026, 3, 7, 18, 30)
    assert shifted_due(before, parent, None) == before


async def test_the_next_occurrence_covers_a_subtask_skipped_today(
    use_case_context: UseCaseDeps, user: User, fake_uow_factory: FakeUowFactory
) -> None:
    review = await _add(
        use_case_context,
        user,
        "Weekly review",
        estimated_minutes=30,
        recurrence=RecurrenceInputDTO(
            frequency=RecurrenceInterval.WEEKLY, start_date="2026-03-06 17:00"
        ),
    )
    [inbox, calendar] = (
        await _add_to(
            use_case_context, user, review, "Inbox", "Calendar", estimated_minutes=15
        )
    ).subtasks
    # Skipped this week (out of the sum), and the other one grows
    await CancelTaskUseCase(**use_case_context).execute(
        CancelTaskInputDTO(task_id_prefix=inbox.id[:8], user_id=str(user.id))
    )
    await _edit(use_case_context, user, calendar, estimated_minutes=20)
    assert (await _entity(fake_uow_factory, review)).estimated_duration_minutes == 30

    await _complete_following(use_case_context, user, review, fake_uow_factory)

    async with fake_uow_factory() as uow:
        [following] = [
            t
            for t in uow.tasks.tasks.values()
            if t.series_id is not None
            and str(t.series_id) == review.id
            and t.status == TaskStatus.PENDING
        ]
    # Both are back next week: 15 + 20
    assert following.estimated_duration_minutes == 35
