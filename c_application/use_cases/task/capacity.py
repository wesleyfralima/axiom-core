"""The commitment limit: how full a day is.

A day has the user's productive day (``day_start`` to ``day_end``) minus a
margin (``day_margin``). Today, it is the clock: what is left from now (or
the day's start) to its end — what is done early leaves more room by
itself. Against it, the estimates of the day's open tasks — the late ones
too, for today — counting a parent only (it covers its subtasks) and never
an hourly series (meant to be quick). A full day warns, never blocks.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from b_domain.entities import Task, User
from b_domain.entities.user import UserPrefs
from b_domain.ports.repositories.filters import TaskFilter
from b_domain.ports.unit_of_work import UnitOfWork
from b_domain.value_objects import TaskStatus, UserId
from b_domain.value_objects.dates import DueDate
from c_application.dtos.task_dtos import DayLoadDTO
from c_application.utils.date_input import local_today


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
    """Whether a task takes time from its day: open, dated, not a subtask
    (its parent covers it), not an hourly series."""
    return (
        not task.status.is_closed
        and task.deleted_at is None
        and task.due_date is not None
        and task.parent_id is None
        and not (task.recurrence is not None and task.recurrence.is_sub_daily)
    )


async def day_load(
    uow: UnitOfWork, user_id: UserId, prefs: UserPrefs, day: date, now: datetime
) -> DayLoadDTO:
    """How full ``day`` is (today: the late tasks count too)."""
    zone: ZoneInfo = _zone(prefs.timezone)
    today: date = local_today(now, prefs.timezone)
    tasks: list[Task] = await uow.tasks.list(
        TaskFilter(
            user_id=user_id,
            exclude_statuses=TaskStatus.closed(),
            has_due_date=True,
            only_roots=True,
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
            planned += task.estimated_duration_minutes
    return DayLoadDTO(
        day=day,
        planned_minutes=planned,
        available_minutes=available_minutes(prefs, day, now),
        is_today=day == today,
    )


async def full_day_of(
    uow: UnitOfWork, user_id: UserId, task: Task, now: datetime
) -> DayLoadDTO | None:
    """The day ``task`` is on, when it is full and the user wants to know;
    else None. A subtask's is its parent's (the parent covers it); a late
    task is today's."""
    user: User | None = await uow.users.get_by_id(user_id)
    prefs: UserPrefs = user.preferences if user else UserPrefs()
    if not prefs.full_day_warnings:
        return None
    if task.parent_id is not None:
        parent: Task | None = await uow.tasks.get_by_id(task.parent_id, user_id)
        if parent is None:
            return None
        task = parent
    if not counts(task):
        return None
    assert task.due_date is not None
    today: date = local_today(now, prefs.timezone)
    day: date = max(_wall(task.due_date, _zone(prefs.timezone)).date(), today)
    load: DayLoadDTO = await day_load(uow, user_id, prefs, day, now)
    return load if load.is_full else None


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
