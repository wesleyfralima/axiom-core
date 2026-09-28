"""A task's relations: its parent and subtasks, and the tasks it depends on.

- **Subtasks** are a parent's checklist, as tasks: one level (a subtask has
  no subtasks), never repeating on their own (a recurring parent brings them
  to its next occurrence), and never "bigger" than their parent — due no
  later, priority no higher, and the parent's estimate covers theirs
  together. The parent rules: moving its due date or lowering its priority
  brings its open subtasks along, and says so.
- **Dependencies** are kept once they are done: a task shows what it waited
  on, and waits again if one of them is reopened. It waits (blocked) while
  one of them is open; a closed or deleted one does not hold it. A task never
  depends, however indirectly, on one that depends on it.
"""

from collections.abc import Iterable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from a_core import UniqueId
from a_core.exceptions import ValidationException
from b_domain.entities import Task
from b_domain.ports.unit_of_work import UnitOfWork
from b_domain.value_objects import TaskId, TaskStatus, UserId
from b_domain.value_objects.dates import DueDate
from c_application.dtos.task_dtos import TaskLinkDTO


def is_open(task: Task | None) -> bool:
    """Still to do: there, not deleted, not done, cancelled or archived."""
    return task is not None and task.deleted_at is None and not task.status.is_closed


async def waits_on_open(
    uow: UnitOfWork, depends_on: Iterable[TaskId], user_id: UserId
) -> bool:
    """Whether one of these tasks is still open (the task waits on it)."""
    for ref in depends_on:
        if is_open(await uow.tasks.get_by_id(ref, user_id)):
            return True
    return False


async def subtasks_of(uow: UnitOfWork, task: Task) -> list[Task]:
    """Every subtask under ``task``, at any depth, the deepest last (none
    deleted)."""
    found: list[Task] = []
    level: list[Task] = [task]
    while level:
        children: list[Task] = []
        for parent in level:
            children.extend(await uow.tasks.get_subtasks(parent.id, limit=10_000))
        found.extend(children)
        level = children
    return found


async def check_parent(
    uow: UnitOfWork, task: Task, parent: Task, user_id: UserId
) -> None:
    """Refuse a parent that is the task itself or one of its subtasks.

    Raises:
        ValidationException: If moving it there would make a loop.
    """
    if parent.id == task.id:
        raise ValidationException("A task cannot be its own parent.")
    ancestor: Task | None = parent
    while ancestor is not None and ancestor.parent_id is not None:
        if ancestor.parent_id == task.id:
            raise ValidationException(
                f"'{parent.title}' is a subtask of '{task.title}': "
                "a task cannot go under its own subtask."
            )
        ancestor = await uow.tasks.get_by_id(ancestor.parent_id, user_id)


async def check_dependency(
    uow: UnitOfWork, task: Task, blocker: Task, user_id: UserId
) -> None:
    """Refuse a dependency that would wait on itself, however indirectly.

    Raises:
        ValidationException: If ``blocker`` is the task, or depends on it.
    """
    if blocker.id == task.id:
        raise ValidationException("A task cannot depend on itself.")
    seen: set[TaskId] = set()
    pending: list[TaskId] = list(blocker.depends_on)
    while pending:
        ref: TaskId = pending.pop()
        if ref == task.id:
            raise ValidationException(
                f"'{blocker.title}' already waits on '{task.title}': "
                "they would wait on each other forever."
            )
        if ref in seen:
            continue
        seen.add(ref)
        found: Task | None = await uow.tasks.get_by_id(ref, user_id)
        if found is not None:
            pending.extend(found.depends_on)


def link(task: Task) -> TaskLinkDTO:
    """A related task, in a few words."""
    return TaskLinkDTO(
        id=str(task.id),
        title=str(task.title),
        status=str(task.status),
        due_date=task.due_date.materialize() if task.due_date else None,
        deleted=task.deleted_at is not None,
    )


async def relations_of(uow: UnitOfWork, task: Task, user_id: UserId) -> dict[str, Any]:
    """What ``show`` tells about a task's relations, as TaskOutputDTO fields:
    its parent, its subtasks (direct, and how many are open at any depth),
    what it waits on and what waits on it."""
    parent: Task | None = (
        await uow.tasks.get_by_id(task.parent_id, user_id) if task.parent_id else None
    )
    children: list[Task] = await uow.tasks.get_subtasks(task.id, limit=10_000)
    below: list[Task] = await subtasks_of(uow, task)
    waits_on: list[Task] = [
        found
        for ref in sorted(task.depends_on, key=str)
        if (found := await uow.tasks.get_by_id(ref, user_id)) is not None
    ]
    blocks: list[Task] = [
        t
        for t in await uow.tasks.find_tasks_blocked_by(task.id)
        if t.user_id == user_id
    ]
    return {
        "parent": link(parent) if parent else None,
        "subtasks": [link(t) for t in children],
        "open_subtasks": sum(1 for t in below if is_open(t)),
        "all_subtasks": len(below),
        "waits_on": [link(t) for t in waits_on],
        "blocks": [link(t) for t in blocks],
    }


# ---------------------------------------------------------------- subtasks


def later_than(due: DueDate | None, limit: DueDate | None) -> bool:
    """Whether ``due`` comes after ``limit`` — no date means never due, the
    latest of all."""
    if limit is None:
        return False
    if due is None:
        return True
    return due.materialize() > limit.materialize()


def same_due(one: DueDate | None, other: DueDate | None) -> bool:
    """Whether two due dates are the same instant (or both none)."""
    if one is None or other is None:
        return one is None and other is None
    return one.materialize() == other.materialize()


def due_text(due: DueDate | None) -> str | None:
    """A due date as the history writes it."""
    return due.value.isoformat() if due else None


def check_takes_subtasks(parent: Task) -> None:
    """Refuse a parent that cannot take a subtask.

    Raises:
        ValidationException: If it is a subtask itself, closed or deleted.
    """
    if parent.deleted_at is not None:
        raise ValidationException(f"'{parent.title}' is deleted: restore it first.")
    if parent.parent_id is not None:
        raise ValidationException(
            f"'{parent.title}' is a subtask: a subtask has no subtasks of its own."
        )
    if parent.status.is_closed:
        raise ValidationException(
            f"'{parent.title}' is {parent.status}: reopen it to add subtasks."
        )


async def check_can_be_subtask(uow: UnitOfWork, task: Task) -> None:
    """Refuse a task that cannot be a subtask.

    Raises:
        ValidationException: If it repeats (its parent would) or has
            subtasks of its own.
    """
    if task.recurrence is not None:
        raise ValidationException(
            f"'{task.title}' repeats, and a subtask does not (its parent "
            "does): stop repeating it first."
        )
    if await uow.tasks.get_subtasks(task.id, limit=1):
        raise ValidationException(
            f"'{task.title}' has subtasks: a subtask has none of its own."
        )


def fit_under(
    now: datetime,
    task: Task,
    parent: Task,
    *,
    due_asked: bool,
    priority_asked: bool,
) -> list[str]:
    """Keep a subtask within its parent: due no later, priority no higher.

    What the user asked for is checked; what they did not ask for (a task
    moved under a parent) is brought within the parent, and said so.

    Args:
        now (datetime): When.
        task (Task): The subtask.
        parent (Task): Its parent.
        due_asked (bool): The user set (or removed) its due date now.
        priority_asked (bool): The user set its priority now.

    Returns:
        list[str]: What changed on its own, to tell the user.

    Raises:
        ValidationException: If what the user asked for is beyond the parent.
    """
    notes: list[str] = []
    if later_than(task.due_date, parent.due_date):
        assert parent.due_date is not None
        if due_asked:
            raise ValidationException(
                "A subtask is due no later than its parent: "
                f"'{parent.title}' is due {parent.due_date.format()}."
            )
        notes.append(
            f"'{task.title}' is now due with its parent."
            if task.due_date is None
            else f"'{task.title}' moved to its parent's due date."
        )
        task.set_due(now, parent.due_date)
    if task.priority > parent.priority:
        level: str = parent.priority.name.lower()
        if priority_asked:
            raise ValidationException(
                "A subtask's priority is no higher than its parent's: "
                f"'{parent.title}' is {level}."
            )
        notes.append(f"'{task.title}' priority lowered to {level}, its parent's.")
        task.update_priority(now, parent.priority)
    return notes


async def subtasks_minutes(
    uow: UnitOfWork, parent: Task, changed: Iterable[Task] = ()
) -> int:
    """How long a parent's subtasks take together (cancelled ones left out).

    Args:
        uow (UnitOfWork): Where they are.
        parent (Task): The parent.
        changed (Iterable[Task]): Subtasks just added or changed, as they
            are now (the stored ones may not show it yet).
    """
    subs: dict[TaskId, Task] = {
        t.id: t for t in await uow.tasks.get_subtasks(parent.id, limit=10_000)
    }
    for task in changed:
        if task.parent_id == parent.id and task.deleted_at is None:
            subs[task.id] = task
    return sum(
        t.estimated_duration_minutes
        for t in subs.values()
        if t.status != TaskStatus.CANCELLED
    )


async def cover_subtasks(
    uow: UnitOfWork,
    now: datetime,
    parent: Task,
    changed: Iterable[Task] = (),
    caused_by: UniqueId | None = None,
) -> str | None:
    """Raise the parent's estimate to what its subtasks take together, when
    they take longer (never lowered: removing one leaves it).

    Args:
        uow (UnitOfWork): Where they are.
        now (datetime): When.
        parent (Task): The parent.
        changed (Iterable[Task]): Subtasks just added or changed.
        caused_by (UniqueId | None): The change that made this one (undone
            with it).

    Returns:
        str | None: What changed, to tell the user.
    """
    total: int = await subtasks_minutes(uow, parent, changed)
    before: int = parent.estimated_duration_minutes
    if total <= before:
        return None
    previous: dict[str, Any] = parent.snapshot()
    parent.update_estimate(now, total)
    parent.record_edit(
        now, {"estimate": (str(before), str(total))}, previous, caused_by=caused_by
    )
    await uow.tasks.update(parent)
    return f"'{parent.title}' now takes {total} min: its subtasks take that long."


async def pull_subtasks(
    uow: UnitOfWork,
    now: datetime,
    parent: Task,
    old_due: DueDate | None,
    caused_by: UniqueId | None,
) -> list[str]:
    """Bring the parent's open subtasks along with its edit.

    A subtask due with the parent (the one it inherited) follows its due
    date wherever it goes — away too; one due later than the new date comes
    to it; one with a higher priority comes down to the parent's. The others
    stay as they are.

    Args:
        uow (UnitOfWork): Where they are.
        now (datetime): When.
        parent (Task): The parent, already edited.
        old_due (DueDate | None): Its due date before the edit.
        caused_by (UniqueId | None): The parent's edit (undone with it).

    Returns:
        list[str]: What changed, to tell the user.
    """
    moved: bool = not same_due(old_due, parent.due_date)
    notes: list[str] = []
    for sub in await uow.tasks.get_subtasks(parent.id, limit=10_000):
        if not is_open(sub):
            continue
        previous: dict[str, Any] = sub.snapshot()
        changes: dict[str, tuple[str | None, str | None]] = {}
        due: DueDate | None = sub.due_date
        if (moved and same_due(due, old_due)) or later_than(due, parent.due_date):
            due = parent.due_date
        if not same_due(due, sub.due_date):
            changes["due"] = (due_text(sub.due_date), due_text(due))
            sub.set_due(now, due)
        if sub.priority > parent.priority:
            changes["priority"] = (
                sub.priority.name.lower(),
                parent.priority.name.lower(),
            )
            sub.update_priority(now, parent.priority)
        if changes:
            sub.record_edit(now, changes, previous, caused_by=caused_by)
            await uow.tasks.update(sub)
            what: str = " and ".join(
                "due date" if name == "due" else name for name in changes
            )
            notes.append(f"'{sub.title}': {what} changed with its parent.")
    return notes


def shifted_due(
    due: DueDate | None, old_parent: DueDate | None, new_parent: DueDate | None
) -> DueDate | None:
    """A subtask's due date under its parent's next occurrence: as far
    before the parent's as it was (with the parent when it was not before).
    """
    if new_parent is None:
        return due
    if due is None or not later_than(old_parent, due):
        return new_parent
    assert old_parent is not None
    if (
        due.is_floating
        and old_parent.is_floating
        and new_parent.is_floating
        and due.timezone == new_parent.timezone == old_parent.timezone
    ):
        # Wall-clock time: 30 minutes before stays 30 minutes before
        return DueDate.floating(
            new_parent.value - (old_parent.value - due.value), due.timezone or "UTC"
        )
    moment: datetime = new_parent.materialize() - (
        old_parent.materialize() - due.materialize()
    )
    if due.is_floating:
        zone: str = due.timezone or "UTC"
        return DueDate.floating(
            moment.astimezone(ZoneInfo(zone)).replace(tzinfo=None), zone
        )
    return DueDate.fixed(moment)
