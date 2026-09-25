from datetime import UTC, datetime
from uuid import uuid4

import pytest

from a_core import InvalidStateTransition
from b_domain.entities import Task, User
from b_domain.value_objects import (
    Description,
    Priority,
    TaskId,
    TaskStatus,
    Title,
    UserId,
)
from c_application.mappers.task_mapper import TaskMapper

# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def user() -> User:
    """Provide a fresh User instance for testing."""
    return User.create(
        now=datetime.now(),
        username="test_user",
        password_hash="fake_hash",
        email="test@test.com",
    )


@pytest.fixture
def task(user: User) -> Task:
    """Provide a fresh Task instance for testing."""
    return Task.create(
        now=datetime.now(),
        user_id=user.id,
        title=Title("Test Task"),
        description=Description("Initial description"),
    )


# ============================================================
# Group 1: Task Creation and Initialization
# ============================================================


@pytest.mark.unit
def test_task_create_initializes_basic_fields(task: Task) -> None:
    """Ensure Task.create initializes core fields correctly."""

    assert isinstance(task.id, TaskId)
    assert task.title.value == "Test Task"
    assert task.description.value == "Initial description"
    assert task.status == TaskStatus.PENDING


@pytest.mark.unit
def test_task_create_sets_timestamps(task: Task) -> None:
    """Ensure Task.create sets created_at and updated_at timestamps."""

    assert isinstance(task.created_at, datetime)
    assert isinstance(task.updated_at, datetime)
    assert task.created_at == task.updated_at


@pytest.mark.unit
def test_task_create_sets_optional_fields_default(task: Task) -> None:
    """Ensure optional fields are set to defaults when not provided."""

    assert task.parent_id is None
    assert task.recurrence is None
    assert task.is_subtask is False


# ============================================================
# Group 2: Field Updates
# ============================================================


@pytest.mark.unit
def test_task_rename_updates_title_and_timestamp(task: Task) -> None:
    """Ensure renaming a task updates its title and timestamp."""

    before: datetime = task.updated_at
    task.rename(
        new_title="New Title",
        now=datetime.now(),
    )

    assert task.title.value == "New Title"
    assert task.updated_at >= before


@pytest.mark.unit
def test_task_update_description_updates_value_and_timestamp(task: Task) -> None:
    """Ensure updating description changes value and updates timestamp."""

    before: datetime = task.updated_at
    task.update_description(new_description="New description", now=datetime.now())

    assert task.description.value == "New description"
    assert task.updated_at >= before


@pytest.mark.unit
def test_task_update_priority(task: Task) -> None:
    """Ensure updating priority changes value and updates timestamp."""

    before: datetime = task.updated_at
    task.update_priority(new_priority=Priority.HIGH, now=datetime.now())

    assert task.priority == Priority.HIGH
    assert task.updated_at >= before


# ============================================================
# Group 3: Status Transitions
# ============================================================


@pytest.mark.unit
def test_mark_task_as_done(task: Task) -> None:
    """Ensure marking a task as done sets status to DONE."""

    task.mark_as_done(datetime.now())
    assert task.status == TaskStatus.DONE


@pytest.mark.unit
def test_mark_task_as_cancelled(task: Task) -> None:
    """Ensure marking a task as canceled sets status to CANCELLED."""

    task.mark_as_cancelled(datetime.now())
    assert task.status == TaskStatus.CANCELLED


@pytest.mark.unit
def test_reopen_task(task: Task) -> None:
    """Ensure reopening a task after completion sets status to REOPENED."""

    now: datetime = datetime.now()
    task.mark_as_done(now)
    task.reopen(now)
    assert task.status == TaskStatus.REOPENED


@pytest.mark.unit
def test_archive_task(task: Task) -> None:
    """Ensure archiving a task sets status to ARCHIVED."""

    task.archive(datetime.now())
    assert task.status == TaskStatus.ARCHIVED


@pytest.mark.unit
def test_invalid_status_transition_raises(task: Task) -> None:
    """Ensure invalid status transitions raise InvalidStateTransition."""

    now: datetime = datetime.now()

    task.mark_as_cancelled(now)
    with pytest.raises(InvalidStateTransition):
        task.mark_as_done(now)


# ============================================================
# Group 4: Subtask Management
# ============================================================


@pytest.mark.unit
def test_add_subtask_when_parent_matches(task: Task, user: User) -> None:
    """Ensure a subtask with matching parent_id can be added."""

    subtask: Task = Task.create(
        now=datetime.now(),
        title=Title("Subtask"),
        parent_id=task.id,
        user_id=user.id,
    )

    task.add_subtask(subtask)

    assert subtask in task._subtasks
    assert subtask.is_subtask is True


@pytest.mark.unit
def test_add_subtask_raises_if_parent_id_mismatch(task: Task, user: User) -> None:
    """
    Ensure adding a subtask with mismatched
    parent_id raises InvalidStateTransition.
    """

    other_task_id: TaskId = TaskId()
    subtask: Task = Task.create(
        now=datetime.now(),
        title=Title("Invalid Subtask"),
        parent_id=other_task_id,
        user_id=user.id,
    )

    with pytest.raises(InvalidStateTransition):
        task.add_subtask(subtask)


# ============================================================
# Group 5: Utility Methods
# ============================================================


@pytest.mark.unit
def test_touch_updates_updated_at(task: Task) -> None:
    """Ensure touch mechanism updates the updated_at timestamp."""

    before: datetime = task.updated_at
    task.rename(new_title="Trigger touch", now=datetime.now())
    assert task.updated_at > before


@pytest.mark.unit
def test_is_subtask_true_when_parent_id_present(user: User) -> None:
    """Ensure is_subtask returns True when parent_id is set."""

    parent_id: TaskId = TaskId()
    task: Task = Task.create(
        now=datetime.now(),
        title=Title("Child task"),
        parent_id=parent_id,
        user_id=user.id,
    )
    assert task.is_subtask is True


@pytest.mark.unit
def test_is_subtask_false_when_no_parent(user: User) -> None:
    """Ensure is_subtask returns False when no parent_id is set."""

    task: Task = Task.create(
        now=datetime.now(),
        title=Title("Root task"),
        user_id=user.id,
    )
    assert task.is_subtask is False


def test_events_carry_the_injected_time() -> None:
    """Rule 4 (time is injected): events are stamped with `now`, not the wall clock."""

    now = datetime(2020, 2, 2, 8, 0, tzinfo=UTC)
    task = Task.create(now=now, user_id=UserId(uuid4()), title=Title("Old"))
    task.mark_as_done(now)

    assert [e.occurred_at for e in task.pull_events()] == [now, now]


def test_output_dto_says_when_the_task_is_blocked() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    blocker = Task.create(now=now, user_id=UserId(uuid4()), title=Title("Before"))
    blocked = Task.create(
        now=now, user_id=blocker.user_id, title=Title("After"), depends_on={blocker.id}
    )

    assert TaskMapper.to_output(blocked, now).is_blocked is True
    assert TaskMapper.to_output(blocker, now).is_blocked is False
