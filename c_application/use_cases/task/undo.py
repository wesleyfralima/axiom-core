"""Undo: take back the user's last command, from the task history.

Undo walks back in time: each run undoes the newest command not undone yet
— every change it made (``task done a b c`` is one command: the three come
back), newest first — so a snapshot is never restored over a later change.
What a change made on its own (the next occurrence of a completed recurring
task) goes with it. Changes from before commands were recorded go back one
at a time.
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
# Made along with another change (a parent's subtasks closed, moved or
# deleted with it; a parent reopened or its estimate raised by a subtask):
# back to the snapshot
_ALONG: frozenset[TaskAction] = frozenset(
    {
        TaskAction.COMPLETED,
        TaskAction.CANCELLED,
        TaskAction.ARCHIVED,
        TaskAction.REOPENED,
        TaskAction.EDITED,
        TaskAction.DELETED,
    }
)


@dataclass(frozen=True, kw_only=True)
class UndoRequest(DTO):
    """Whose last change to undo; ``entry_id`` is the one the preview showed
    (the undo refuses if something changed since)."""

    user_id: str
    entry_id: str | None = None


@dataclass(frozen=True, kw_only=True)
class UndoItemDTO(DTO):
    """One more change of the command undo takes back.

    Attributes:
        entry (TaskHistoryEntryDTO): The change.
        task_id (str): The task it changed.
        title (str): The task's title now.
    """

    entry: TaskHistoryEntryDTO
    task_id: str
    title: str


@dataclass(frozen=True, kw_only=True)
class UndoPreviewOutputDTO(DTO):
    """What ``undo`` would take back, and whether it can.

    Attributes:
        entry (TaskHistoryEntryDTO | None): The command's newest change;
            None: nothing to undo.
        entry_id (str | None): Its identity, to pass to the undo.
        task_id (str | None): The task it changed.
        title (str | None): The task's title now.
        more (list[UndoItemDTO]): The command's other changes, newest first
            (``task done a b c``: b and a).
        also (list[str]): What goes with it (the titles of tasks the change
            made on its own).
        along (list[str]): What comes back as it was with it (the titles of
            tasks the change changed along — a parent's subtasks closed,
            moved or deleted with it; a parent a subtask changed).
        blocked (str | None): Why it cannot be undone, if it cannot.
    """

    entry: TaskHistoryEntryDTO | None = None
    entry_id: str | None = None
    task_id: str | None = None
    title: str | None = None
    more: list[UndoItemDTO] = field(default_factory=list)
    also: list[str] = field(default_factory=list)
    along: list[str] = field(default_factory=list)
    blocked: str | None = None


@dataclass(frozen=True, kw_only=True)
class UndoneItemDTO(DTO):
    """One more change undone with the command's newest."""

    task_id: str
    title: str
    action: str


@dataclass(frozen=True, kw_only=True)
class UndoOutputDTO(DTO):
    """What was undone: the command's newest change, its others (``more``)
    and how many tasks went or came back along with them."""

    task_id: str
    title: str
    action: str
    also_removed: int = 0
    more: list[UndoneItemDTO] = field(default_factory=list)


class UndoPreviewUseCase(UseCase[UndoRequest, UndoPreviewOutputDTO]):
    """Show what ``undo`` would take back."""

    async def execute(self, request: UndoRequest) -> UndoPreviewOutputDTO:
        user_id: UserId = UserId.from_string(
            request.user_id, error_msg="Invalid user ID."
        )
        async with self.uow as uow:
            command: list[TaskHistoryEntry] = await _last_command(uow, user_id)
            if not command:
                return UndoPreviewOutputDTO()
            target: TaskHistoryEntry = command[0]
            tasks: list[Task | None] = [
                await uow.tasks.get_by_id(e.task_id, user_id) for e in command
            ]
            caused: list[Task] = []
            along: list[Task] = []
            for entry in command:
                made, changed = await _made_by(uow, entry, user_id)
                caused += made
                along += changed
            task: Task | None = tasks[0]
            return UndoPreviewOutputDTO(
                entry=history_entry_to_dto(target),
                entry_id=str(target.entry_id),
                task_id=str(target.task_id),
                title=str(task.title) if task else target.note,
                more=[
                    UndoItemDTO(
                        entry=history_entry_to_dto(e),
                        task_id=str(e.task_id),
                        title=str(t.title) if t else (e.note or ""),
                    )
                    for e, t in zip(command[1:], tasks[1:], strict=True)
                ],
                also=[str(t.title) for t in caused],
                along=[str(t.title) for t in along],
                blocked=next(
                    (
                        reason
                        for e, t in zip(command, tasks, strict=True)
                        if (reason := _why_not(e, t))
                    ),
                    None,
                )
                or await _changed_elsewhere(uow, command, user_id),
            )


class UndoUseCase(UseCase[UndoRequest, UndoOutputDTO]):
    """Take back the user's last command (the one the preview showed)."""

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
            command: list[TaskHistoryEntry] = await _last_command(uow, user_id)
            if not command:
                raise ValidationException("Nothing to undo.")
            if request.entry_id and str(command[0].entry_id) != request.entry_id:
                raise ValidationException(
                    "Something changed since: run undo again to see what it undoes."
                )
            tasks: list[Task] = []
            for entry in command:
                task: Task | None = await uow.tasks.get_by_id(entry.task_id, user_id)
                reason: str | None = _why_not(entry, task)
                if reason or task is None:
                    raise DomainException(reason or "The task is gone.")
                tasks.append(task)

            # A snapshot never goes back over what another device did since
            if reason := await _changed_elsewhere(uow, command, user_id):
                raise DomainException(reason)

            # Newest first: each snapshot goes back over what came after it
            also: int = 0
            for entry, task in zip(command, tasks, strict=True):
                also += await _undo_one(uow, entry, task, user_id, now)

            return UndoOutputDTO(
                task_id=str(tasks[0].id),
                title=str(tasks[0].title),
                action=str(command[0].action),
                also_removed=also,
                more=[
                    UndoneItemDTO(
                        task_id=str(t.id), title=str(t.title), action=str(e.action)
                    )
                    for e, t in zip(command[1:], tasks[1:], strict=True)
                ],
            )


async def _undo_one(
    uow: UnitOfWork,
    target: TaskHistoryEntry,
    task: Task,
    user_id: UserId,
    now: datetime,
) -> int:
    """Undo one change of the command; how many tasks went or came back along
    with it."""
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
    return also


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


def _undoable(entry: TaskHistoryEntry, undone: set[UUID], device: UUID | None) -> bool:
    """A change of the user's own, made on this device, and not undone yet (a
    change another device made and sync brought is theirs to undo; one made
    along with another goes with that one)."""
    return not (
        entry.action == TaskAction.UNDONE
        or entry.entry_id in undone
        or entry.caused_by is not None
        or entry.device_id not in (None, device)
    )


def _last_undoable(
    recent: list[TaskHistoryEntry], device: UUID | None = None
) -> TaskHistoryEntry | None:
    """The newest change that can be undone."""
    undone = {e.undoes for e in recent if e.undoes is not None}
    return next((e for e in recent if _undoable(e, undone, device)), None)


async def _last_command(uow: UnitOfWork, user_id: UserId) -> list[TaskHistoryEntry]:
    """The changes of the newest command that can be undone, newest first
    (one change alone when it was made before commands were recorded)."""
    recent: list[TaskHistoryEntry] = await uow.task_history.recent(user_id)
    device: UUID | None = await _this_device(uow)
    target: TaskHistoryEntry | None = _last_undoable(recent, device)
    if target is None:
        return []
    if target.command_id is None:
        return [target]
    undone = {e.undoes for e in recent if e.undoes is not None}
    return [
        e
        for e in await uow.task_history.of_command(target.command_id)
        if e.user_id == user_id and _undoable(e, undone, device)
    ]


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


async def _caused(uow: UnitOfWork, entry_id: UUID) -> list[TaskHistoryEntry]:
    """Everything a change made on its own, at any depth."""
    found: list[TaskHistoryEntry] = []
    for entry in await uow.task_history.caused_by(entry_id):
        found.append(entry)
        found.extend(await _caused(uow, entry.entry_id))
    return found


async def _changed_elsewhere(
    uow: UnitOfWork, command: list[TaskHistoryEntry], user_id: UserId
) -> str | None:
    """Why the command cannot be undone here: a task it changed — or made, or
    closed along — was changed on another device after it. Undo restores a
    whole snapshot, so it would take that change away too (and a next
    occurrence the other device changed would go with its tombstone). None
    when nothing changed elsewhere since."""
    device: UUID | None = await _this_device(uow)
    for entry in command:
        touched: list[TaskHistoryEntry] = [entry, *await _caused(uow, entry.entry_id)]
        for each in touched:
            for later in await uow.task_history.list_for_task(each.task_id, user_id):
                if later.occurred_at > entry.occurred_at and later.device_id not in (
                    None,
                    device,
                ):
                    task: Task | None = await uow.tasks.get_by_id(each.task_id, user_id)
                    return (
                        f"'{task.title if task else each.note}' was changed on "
                        "another device after that: undoing it here would take "
                        "that change away too. Change it back by hand."
                    )
    return None


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
