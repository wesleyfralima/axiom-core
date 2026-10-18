"""The commitment limit: how full a day is.

A day has the user's productive day (``day_start`` to ``day_end``) minus a
margin (``day_margin``). Today, it is the clock: what is left from now (or
the day's start) to its end — what is done early leaves more room by
itself. Against it, the estimates of the day's open tasks — the late ones
too, for today — never an hourly series (meant to be quick). A full day
warns, never blocks.

**A subtask counts on its own day**, and its parent only its own part
(``own_minutes``): its estimate (the plan, never lowered) minus every
subtask's — open, done or cancelled: a done one was spent on its day, a
cancelled one is gone. Worked out each time, never stored.
"""

from collections.abc import Iterable
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from b_domain.entities import Task, User
from b_domain.entities.user import UserPrefs
from b_domain.ports.repositories.filters import TaskFilter
from b_domain.ports.unit_of_work import UnitOfWork
from b_domain.value_objects import TaskId, TaskStatus, UserId
from b_domain.value_objects.dates import DueDate
from b_domain.value_objects.task_history import TaskAction, TaskHistoryEntry
from c_application.dtos.task_dtos import DayLoadDTO, TaskOutputDTO
from c_application.utils.date_input import local_today
from c_application.utils.prefs import prefs_of


def available_minutes(prefs: UserPrefs, day: date, now: datetime) -> int:
    """The time a day has for tasks: today, what is left of it; another
    day, all of it — minus the margin."""
    zone: ZoneInfo = _zone(prefs.timezone)
    if day != local_today(now, prefs.timezone):
        return prefs.day_capacity_minutes
    hours, minutes = (int(p) for p in prefs.day_start.split(":"))
    start: datetime = datetime.combine(day, time(hours, minutes), tzinfo=zone)
    end: datetime = start + timedelta(minutes=prefs.day_minutes)
    moment: datetime = now if now.tzinfo else now.replace(tzinfo=ZoneInfo("UTC"))
    if moment <= start:
        return prefs.day_capacity_minutes
    left: int = max(int((end - moment).total_seconds() // 60), 0)
    return left * (100 - prefs.day_margin) // 100


def counts(task: Task) -> bool:
    """Whether a task takes time from its day: open, dated, not an hourly
    series. A subtask counts on its own day; its parent, its own part."""
    return (
        not task.status.is_closed
        and task.deleted_at is None
        and task.due_date is not None
        and not (task.recurrence is not None and task.recurrence.is_sub_daily)
    )


async def own_minutes(uow: UnitOfWork, task: Task) -> int:
    """The part of ``task``'s estimate that is its own, on its day: a
    parent's own part (``own_part``); anything else, its whole estimate."""
    own: int | None = await own_part(uow, task)
    return task.estimated_duration_minutes if own is None else own


async def own_part(
    uow: UnitOfWork, task: Task, subs: list[Task] | None = None
) -> int | None:
    """A parent's own part of its estimate; None for a task with no
    subtasks (or a subtask): all of it is its own.

    Its estimate minus every subtask's (open, done or cancelled), never
    below zero. Every subtask cancelled (none open, none done) and nothing
    of its own left: the estimate of the one cancelled last — the last step
    left became the parent's to do.

    Args:
        uow (UnitOfWork): Where the tasks are.
        task (Task): The task.
        subs (list[Task] | None): Its subtasks, when already read.
    """
    if task.parent_id is not None:
        return None
    if subs is None:
        subs = await uow.tasks.get_subtasks(task.id, limit=10_000)
    if not subs:
        return None
    own: int = max(
        task.estimated_duration_minutes
        - sum(s.estimated_duration_minutes for s in subs),
        0,
    )
    if own or any(s.status != TaskStatus.CANCELLED for s in subs):
        return own
    last: Task | None = await _cancelled_last(uow, task.user_id, subs)
    return last.estimated_duration_minutes if last is not None else 0


async def with_parts(
    uow: UnitOfWork, task: Task, output: TaskOutputDTO
) -> TaskOutputDTO:
    """A parent's output with its own part and its subtasks counted (open
    and all), where a list shows it without its tree (``today``,
    ``wrap``); anything else as it was."""
    if task.parent_id is not None:
        return output
    subs: list[Task] = await uow.tasks.get_subtasks(task.id, limit=10_000)
    if not subs:
        return output
    return replace(
        output,
        own_minutes=await own_part(uow, task, subs),
        open_subtasks=sum(1 for s in subs if not s.status.is_closed),
        all_subtasks=len(subs),
    )


async def _cancelled_last(
    uow: UnitOfWork, user_id: UserId, subs: list[Task]
) -> Task | None:
    """Of these cancelled subtasks, the one cancelled last: its latest
    cancel not undone (several in one command: the last one written). None
    when the history has none (cancelled before it existed)."""
    entries: list[TaskHistoryEntry] = await uow.task_history.list_for_tasks(
        [s.id for s in subs], user_id
    )
    undone: set[UUID] = {
        e.undoes for e in entries if e.action == TaskAction.UNDONE and e.undoes
    }
    by_id: dict[TaskId, Task] = {s.id: s for s in subs}
    for entry in reversed(entries):
        if entry.action == TaskAction.CANCELLED and entry.entry_id not in undone:
            return by_id.get(entry.task_id)
    return None


async def day_load(
    uow: UnitOfWork, user_id: UserId, prefs: UserPrefs, day: date, now: datetime
) -> DayLoadDTO:
    """How full ``day`` is (today: the late tasks count too): each task's
    own part, a subtask's on its own day."""
    zone: ZoneInfo = _zone(prefs.timezone)
    today: date = local_today(now, prefs.timezone)
    tasks: list[Task] = await uow.tasks.list(
        TaskFilter(
            user_id=user_id,
            exclude_statuses=TaskStatus.closed(),
            has_due_date=True,
            limit=10_000,
        )
    )
    planned: int = 0
    for task in tasks:
        if not counts(task):
            continue
        assert task.due_date is not None
        on: date = _wall(task.due_date, zone).date()
        if on == day or (day == today and on < today):
            planned += await own_minutes(uow, task)
    return DayLoadDTO(
        day=day,
        planned_minutes=planned,
        available_minutes=available_minutes(prefs, day, now),
        is_today=day == today,
    )


async def full_day_of(
    uow: UnitOfWork,
    user_id: UserId,
    task: Task,
    now: datetime,
    also: Iterable[Task] = (),
) -> DayLoadDTO | None:
    """The first full day of those ``task`` and ``also`` are on, when the
    user wants to know; else None. A late task's day is today; one that
    does not count (closed, undated, hourly) is on none.

    Args:
        uow (UnitOfWork): Where the tasks are.
        user_id (UserId): Their owner.
        task (Task): The task the change was made to.
        now (datetime): When.
        also (Iterable[Task]): Other tasks whose part the change may have
            grown (a subtask's parent). A parent's subtasks that follow its
            due date are on its day already.
    """
    user: User | None = await uow.users.get_by_id(user_id)
    prefs: UserPrefs = prefs_of(uow, user)
    if not prefs.full_day_warnings:
        return None
    today: date = local_today(now, prefs.timezone)
    zone: ZoneInfo = _zone(prefs.timezone)
    days: set[date] = {
        max(_wall(t.due_date, zone).date(), today)
        for t in (task, *also)
        if counts(t) and t.due_date is not None
    }
    for day in sorted(days):
        load: DayLoadDTO = await day_load(uow, user_id, prefs, day, now)
        if load.is_full:
            return load
    return None


async def parent_of(uow: UnitOfWork, task: Task, user_id: UserId) -> list[Task]:
    """A subtask's parent, as a list (none for a task of its own)."""
    if task.parent_id is None:
        return []
    parent: Task | None = await uow.tasks.get_by_id(task.parent_id, user_id)
    return [parent] if parent is not None else []


def _zone(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _wall(due: DueDate, zone: ZoneInfo) -> datetime:
    """A due date as wall-clock time where the user is."""
    if due.is_floating:
        return due.value
    return due.value.astimezone(zone).replace(tzinfo=None)
