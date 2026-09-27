"""A task's relations: its parent and subtasks, and the tasks it depends on.

- **Subtasks** go any depth (a subtask of a subtask). A task is never moved
  under one of its own subtasks.
- **Dependencies** are kept once they are done: a task shows what it waited
  on, and waits again if one of them is reopened. It waits (blocked) while
  one of them is open; a closed or deleted one does not hold it. A task never
  depends, however indirectly, on one that depends on it.
"""

from collections.abc import Iterable
from typing import Any

from a_core.exceptions import ValidationException
from b_domain.entities import Task
from b_domain.ports.unit_of_work import UnitOfWork
from b_domain.value_objects import TaskId, UserId
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
