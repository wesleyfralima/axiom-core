"""The procrastination radar: a task put off again and again asks for a
decision — do it, split it, or drop it.

Two signals, from what is already recorded (nothing new is collected):

- **Put off** (``postponed``): how many times this task — this occurrence,
  for a recurring one — was snoozed, or had its due date moved later by an
  edit. Only the user's own changes count (not a subtask moved along with
  its parent) and an undone one does not.
- **Missed in a row** (``missed_in_row``, a recurring task): its series'
  latest occurrences not done — skipped, or missed (a habit skips them when
  one is done late) — up to the last done, this one included when its day
  is gone.

Either reaching ``RADAR_AFTER`` flags the task. The user can turn the
warnings off (the ``postpone_warnings`` preference).
"""

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from a_core import DTO
from b_domain.entities import Task
from b_domain.entities.user import UserPrefs
from b_domain.ports.repositories.filters import TaskFilter
from b_domain.ports.unit_of_work import UnitOfWork
from b_domain.value_objects import TaskId, TaskStatus, UserId
from b_domain.value_objects.dates import DueDate
from b_domain.value_objects.task_history import TaskAction, TaskHistoryEntry
from c_application.utils.work_calendar import use_work_calendar

RADAR_AFTER: int = 3
"""From how many times put off (or missed in a row) a task is flagged."""

# How many occurrences between two to count, at most (a long gap is a lot)
_GAP_LIMIT: int = 366


@dataclass(frozen=True, kw_only=True)
class RadarDTO(DTO):
    """A task the radar flags, and why."""

    task_id: str
    title: str
    # Times this task (this occurrence) was put off
    postponed: int = 0
    # A recurring task: its series' occurrences in a row not done
    missed_in_row: int = 0


async def radar_of(
    uow: UnitOfWork,
    user_id: UserId,
    prefs: UserPrefs,
    tasks: list[Task],
    today: date,
    zone: ZoneInfo,
) -> dict[TaskId, RadarDTO]:
    """The flagged ones among ``tasks`` (none when the user turned the
    warnings off)."""
    if not prefs.postpone_warnings:
        return {}
    flagged: dict[TaskId, RadarDTO] = {}
    for task in tasks:
        postponed: int = _postponed(
            await uow.task_history.list_for_task(task.id, user_id)
        )
        missed: int = (
            await _missed_in_row(uow, user_id, prefs, task, today, zone)
            if task.series_id is not None
            else 0
        )
        if postponed >= RADAR_AFTER or missed >= RADAR_AFTER:
            flagged[task.id] = RadarDTO(
                task_id=str(task.id),
                title=str(task.title),
                postponed=postponed,
                missed_in_row=missed,
            )
    return flagged


def _postponed(entries: list[TaskHistoryEntry]) -> int:
    """Times put off: snoozed, or its due date moved later by an edit — the
    user's own changes, not undone."""
    undone: set[object] = {e.undoes for e in entries if e.undoes is not None}
    count: int = 0
    for entry in entries:
        if entry.entry_id in undone or entry.caused_by is not None:
            continue
        if entry.action == TaskAction.SNOOZED:
            count += 1
        elif entry.action == TaskAction.EDITED and any(
            c.field == "due" and _later(c.before, c.after) for c in entry.changes
        ):
            count += 1
    return count


def _later(before: str | None, after: str | None) -> bool:
    """Whether a due date (as the history writes it) moved later."""
    if not before or not after:
        return False
    try:
        old: datetime = datetime.fromisoformat(before)
        new: datetime = datetime.fromisoformat(after)
    except ValueError:
        return False
    return new.replace(tzinfo=None) > old.replace(tzinfo=None)


async def _missed_in_row(
    uow: UnitOfWork,
    user_id: UserId,
    prefs: UserPrefs,
    task: Task,
    today: date,
    zone: ZoneInfo,
) -> int:
    """The series' latest occurrences not done, back to the last done one:
    skipped ones, the ones a habit skipped between two (never made), and
    this one when its day is gone."""
    assert task.series_id is not None
    members: list[Task] = await uow.tasks.list(
        TaskFilter(user_id=user_id, series_id=task.series_id, limit=10_000)
    )
    await use_work_calendar(uow, user_id, prefs, members)
    closed: list[Task] = sorted(
        (
            m
            for m in members
            if m.id != task.id
            and m.status in (TaskStatus.DONE, TaskStatus.CANCELLED)
            and _slot(m) is not None
        ),
        key=lambda m: _slot_value(m),
    )
    missed: int = _gone(task, today, zone)
    later: Task = task
    for before in reversed(closed):
        if _slot_value(before) >= _slot_value(later):
            continue
        missed += _between(before, later)
        if before.status == TaskStatus.DONE:
            break
        missed += 1
        later = before
    return missed


def _wall(due: DueDate, zone: ZoneInfo) -> datetime:
    """A due date as wall-clock time where the user is."""
    if due.is_floating:
        return due.value
    return due.value.astimezone(zone).replace(tzinfo=None)


def _gone(task: Task, today: date, zone: ZoneInfo) -> int:
    """This occurrence and the ones its rule had after it, when their day is
    gone and it is still open (a habit will skip them all when done)."""
    slot: DueDate | None = _slot(task)
    if slot is None or _wall(slot, zone).date() >= today:
        return 0
    count: int = 1
    current: datetime = slot.value
    for _ in range(_GAP_LIMIT if task.recurrence else 0):
        assert task.recurrence is not None
        following: datetime | None = task.recurrence.get_next_occurrence(
            last_occurrence=current
        )
        if following is None or _day_of(following, zone) >= today:
            break
        count += 1
        current = following
    return count


def _day_of(moment: datetime, zone: ZoneInfo) -> date:
    """The user's day of a rule's occurrence (wall-clock, or an instant)."""
    if moment.tzinfo is None:
        return moment.date()
    return moment.astimezone(zone).date()


def _slot(task: Task) -> DueDate | None:
    """Where an occurrence belongs in its series: its due date before any
    snooze."""
    return task.snoozed_from or task.due_date


def _slot_value(task: Task) -> datetime:
    slot: DueDate | None = _slot(task)
    assert slot is not None
    return slot.value.replace(tzinfo=None)


def _between(before: Task, after: Task) -> int:
    """The occurrences ``before``'s rule had between the two, never made (a
    habit done late skips them)."""
    if before.recurrence is None:
        return 0
    first: DueDate | None = _slot(before)
    last: DueDate | None = _slot(after)
    if first is None or last is None:
        return 0
    count: int = 0
    current: datetime = first.value
    for _ in range(_GAP_LIMIT):
        following: datetime | None = before.recurrence.get_next_occurrence(
            last_occurrence=current
        )
        if following is None or following.replace(tzinfo=None) >= last.value.replace(
            tzinfo=None
        ):
            break
        count += 1
        current = following
    return count
