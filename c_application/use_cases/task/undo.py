"""Undo: take back the user's last change, from the task history.

Undo walks back in time: each run undoes the newest change not undone yet,
so a snapshot is never restored over a later change. What a change made on
its own (the next occurrence of a completed recurring task) goes with it.
"""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from a_core import DTO, DomainException, UniqueId
from a_core.exceptions import ValidationException
from b_domain.entities import Task, TimeEntry
from b_domain.ports.repositories.filters import TimeEntryFilter
from b_domain.ports.unit_of_work import UnitOfWork
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import UserId
from b_domain.value_objects.identifiers import TimeEntryId
from b_domain.value_objects.sync import SyncState
from b_domain.value_objects.task_history import TaskAction, TaskHistoryEntry
from c_application.dtos.task_dtos import TaskHistoryEntryDTO
from c_application.mappers.history_mapper import history_entry_to_dto

# Undone by taking the task away (a tombstone), not by a snapshot
_TAKE_AWAY: frozenset[TaskAction] = frozenset({TaskAction.CREATED, TaskAction.RESTORED})
# Made along with another change (a parent's subtasks): back to the snapshot
_ALONG: frozenset[TaskAction] = frozenset({TaskAction.COMPLETED, TaskAction.DELETED})


@dataclass(frozen=True, kw_only=True)
class UndoRequest(DTO):
    """Whose last change to undo; ``entry_id`` is the one the preview showed
    (the undo refuses if something changed since)."""

    user_id: str
    entry_id: str | None = None


@dataclass(frozen=True, kw_only=True)
class UndoPreviewOutputDTO(DTO):
    """What ``undo`` would take back, and whether it can.

    Attributes:
        entry (TaskHistoryEntryDTO | None): The change; None: nothing to undo.
        entry_id (str | None): Its identity, to pass to the undo.
        task_id (str | None): The task it changed.
        title (str | None): The task's title now.
        also (list[str]): What goes with it (the titles of tasks the change
            made on its own).
        along (list[str]): What comes back as it was with it (the titles of
            tasks the change closed or deleted along — a parent's subtasks).
        blocked (str | None): Why it cannot be undone, if it cannot.
    """

    entry: TaskHistoryEntryDTO | None = None
    entry_id: str | None = None
    task_id: str | None = None
    title: str | None = None
    also: list[str] = field(default_factory=list)
    along: list[str] = field(default_factory=list)
    blocked: str | None = None


@dataclass(frozen=True, kw_only=True)
class UndoOutputDTO(DTO):
    """What was undone."""

    task_id: str
    title: str
    action: str
    also_removed: int = 0


class UndoPreviewUseCase(UseCase[UndoRequest, UndoPreviewOutputDTO]):
    """Show what ``undo`` would take back."""

    async def execute(self, request: UndoRequest) -> UndoPreviewOutputDTO:
        user_id: UserId = UserId.from_string(
            request.user_id, error_msg="Invalid user ID."
        )
        async with self.uow as uow:
            target: TaskHistoryEntry | None = _last_undoable(
                await uow.task_history.recent(user_id), await _this_device(uow)
            )
            if target is None:
                return UndoPreviewOutputDTO()
            task: Task | None = await uow.tasks.get_by_id(target.task_id, user_id)
            caused, along = await _made_by(uow, target, user_id)
            return UndoPreviewOutputDTO(
                entry=history_entry_to_dto(target),
                entry_id=str(target.entry_id),
                task_id=str(target.task_id),
                title=str(task.title) if task else target.note,
                also=[str(t.title) for t in caused],
                along=[str(t.title) for t in along],
                blocked=_why_not(target, task),
            )


class UndoUseCase(UseCase[UndoRequest, UndoOutputDTO]):
    """Take back the user's last change (the one the preview showed)."""

    async def execute(self, request: UndoRequest) -> UndoOutputDTO:
        """Undo it.

        Raises:
            ValidationException: If there is nothing to undo, or the last
                change is no longer the one the preview showed.
            DomainException: If it cannot be undone (see the preview's
                ``blocked``).
        """
        user_id: UserId = UserId.from_string(
            request.user_id, error_msg="Invalid user ID."
        )
        now: datetime = self.clock.now()

        async with self.uow as uow:
            target: TaskHistoryEntry | None = _last_undoable(
                await uow.task_history.recent(user_id), await _this_device(uow)
            )
            if target is None:
                raise ValidationException("Nothing to undo.")
            if request.entry_id and str(target.entry_id) != request.entry_id:
                raise ValidationException(
                    "Something changed since: run undo again to see what it undoes."
                )
            task: Task | None = await uow.tasks.get_by_id(target.task_id, user_id)
            reason: str | None = _why_not(target, task)
            if reason or task is None:
                raise DomainException(reason or "The task is gone.")

            # What the change made on its own goes first
            also: int = await _undo_along(uow, target.entry_id, user_id, now)

            # Timers: a start's session is discarded; a pause's runs again
            if target.action == TaskAction.STARTED:
                for session in await uow.time_entries.get_actives_for_task(task.id):
                    await uow.time_entries.delete(TimeEntryId(session.id.value))
            if target.action == TaskAction.PAUSED:
                await _resume_session(uow, task, target)

            snapshot = None if target.action in _TAKE_AWAY else target.previous
            task.revert_to(
                now,
                snapshot,
                UniqueId(target.entry_id),
                str(target.action),
                running=target.action == TaskAction.PAUSED,
            )
            await uow.tasks.update(task)

            return UndoOutputDTO(
                task_id=str(task.id),
                title=str(task.title),
                action=str(target.action),
                also_removed=also,
            )


async def _resume_session(uow: UnitOfWork, task: Task, pause: TaskHistoryEntry) -> None:
    """Run again the session a pause closed (the last one closed by then)."""
    closed: list[TimeEntry] = [
        e
        for e in await uow.time_entries.search(
            TimeEntryFilter(task_id=task.id, limit=10_000)
        )
        if e.end_time is not None and e.end_time <= pause.occurred_at
    ]
    if closed:
        session: TimeEntry = max(closed, key=lambda e: e.end_time or e.start_time)
        session.resume()
        await uow.time_entries.update(session)


async def _this_device(uow: UnitOfWork) -> UUID | None:
    """This device, once it syncs (None before)."""
    state: SyncState | None = await uow.sync.state()
    return state.device_id if state else None


def _last_undoable(
    recent: list[TaskHistoryEntry], device: UUID | None = None
) -> TaskHistoryEntry | None:
    """The newest change that is the user's own, made on this device, and not
    undone yet (a change another device made and sync brought is theirs to
    undo)."""
    undone = {e.undoes for e in recent if e.undoes is not None}
    for entry in recent:
        if (
            entry.action == TaskAction.UNDONE
            or entry.entry_id in undone
            or entry.caused_by is not None
            or entry.device_id not in (None, device)
        ):
            continue
        return entry
    return None


async def _made_by(
    uow: UnitOfWork, target: TaskHistoryEntry, user_id: UserId
) -> tuple[list[Task], list[Task]]:
    """The tasks ``target``'s change changed on its own: the ones it created
    or brought back (still there: undo takes them away), and the ones it
    closed or deleted along with it (subtasks: undo brings them back)."""
    made: list[Task] = []
    along: list[Task] = []
    for entry in await uow.task_history.caused_by(target.entry_id):
        task: Task | None = await uow.tasks.get_by_id(entry.task_id, user_id)
        if task is None:
            continue
        if entry.action in _TAKE_AWAY and task.deleted_at is None:
            made.append(task)
        elif entry.action in _ALONG:
            along.append(task)
    return made, along


async def _undo_along(
    uow: UnitOfWork, entry_id: UUID, user_id: UserId, now: datetime
) -> int:
    """Undo what the change ``entry_id`` made on its own; how many tasks.

    What it created or brought back goes; what it closed or deleted along
    with it (a parent's subtasks) comes back as it was — and what those made
    in turn (a recurring subtask's next occurrence) goes; what it paused runs
    again.
    """
    count: int = 0
    for entry in await uow.task_history.caused_by(entry_id):
        task: Task | None = await uow.tasks.get_by_id(entry.task_id, user_id)
        if task is None:
            continue
        if entry.action in _TAKE_AWAY:
            if task.deleted_at is None:
                task.revert_to(now, None, UniqueId(entry_id), str(TaskAction.CREATED))
                await uow.tasks.update(task)
                count += 1
        elif entry.action in _ALONG and entry.previous is not None:
            count += await _undo_along(uow, entry.entry_id, user_id, now)
            task.revert_to(
                now, entry.previous, UniqueId(entry.entry_id), str(entry.action)
            )
            await uow.tasks.update(task)
            count += 1
        elif entry.action == TaskAction.PAUSED:
            await _resume_session(uow, task, entry)
            task.revert_to(
                now,
                entry.previous,
                UniqueId(entry.entry_id),
                str(TaskAction.PAUSED),
                running=True,
            )
            await uow.tasks.update(task)
    return count


def _why_not(target: TaskHistoryEntry, task: Task | None) -> str | None:
    """Why ``target`` cannot be undone, or None when it can."""
    if task is None:
        return "The task was deleted for good (purged): it cannot come back."
    if target.action not in _TAKE_AWAY and target.previous is None:
        return (
            f"That change ({target.action}) was made before undo existed; "
            "only changes from now on can be undone."
        )
    return None
