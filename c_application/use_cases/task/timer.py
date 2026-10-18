"""Timers: `task start` and `task pause` — one thing at a time.

**One timer at a time, enforced:** a start is refused while any timer
runs (``TimerRunningError``) — it is paused first, never on its own. A
start or a pause may say when it happened (``at``: never in the future): a
start may be before the task was created, never inside another session (no
time counts twice); a pause never before its start. A pause can
**discard** its session: stopped, kept, counted nowhere.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from a_core import DTO
from a_core.exceptions import InvalidStateTransition, ValidationException
from b_domain.entities import Task, TimeEntry, User
from b_domain.entities.user import UserPrefs
from b_domain.exceptions import TimerRunningError
from b_domain.ports.repositories.filters import TimeEntryFilter
from b_domain.ports.unit_of_work import UnitOfWork
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import TaskId, UserId
from c_application.dtos import TaskOutputDTO
from c_application.mappers.task_mapper import TaskMapper
from c_application.utils.date_input import DateInput, past_moment
from c_application.utils.prefs import prefs_of
from c_application.utils.task_utils import find_task


@dataclass(frozen=True, kw_only=True)
class TimerRequest(DTO):
    """Start or pause one task's timer.

    Attributes:
        task_id_prefix (str): The task's ID or ID prefix.
        user_id (str): Its owner.
        at (DateInput | None): When it happened, as typed (a time alone is
            today; never in the future); None: now.
        discard (bool): A pause that counts nothing (the session is kept,
            marked discarded).
    """

    task_id_prefix: str
    user_id: str
    at: DateInput | None = None
    discard: bool = False


@dataclass(frozen=True, kw_only=True)
class TaskTimerOutputDTO(DTO):
    """A timer started or stopped.

    Attributes:
        task (TaskOutputDTO): The task, with its time.
        session_minutes (int | None): The session that just ended (pause).
        started_at (datetime | None): When the session started (start).
        stopped_at (datetime | None): When it stopped (pause).
        discarded (bool): The pause discarded the session (it counts
            nothing).
    """

    task: TaskOutputDTO
    session_minutes: int | None = None
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    discarded: bool = False


class StartTaskUseCase(UseCase[TimerRequest, TaskTimerOutputDTO]):
    """Start working on a task: a timer runs — refused while another runs."""

    async def execute(self, request: TimerRequest) -> TaskTimerOutputDTO:
        """Start the task, now or when ``at`` says.

        Raises:
            ValidationException: If the user ID or the prefix is invalid,
                the moment is in the future or inside another session.
            EntityNotFound: If the user has no such task.
            TimerRunningError: If a timer runs, this task's or another's.
            InvalidStateTransition: If it cannot start (closed, waiting on
                other tasks).
        """
        user_id: UserId = UserId.from_string(
            request.user_id, error_msg="Invalid user ID."
        )
        now: datetime = self.clock.now()

        async with self.uow as uow:
            task: Task = await find_task(uow, request.task_id_prefix, user_id)
            running: TimeEntry | None = await uow.time_entries.get_active_for_user(
                user_id
            )
            if running is not None:
                owner: Task | None = await uow.tasks.get_by_id(running.task_id, user_id)
                raise TimerRunningError(
                    str(running.task_id),
                    str(owner.title) if owner else "a deleted task",
                    _aware(running.start_time),
                )
            moment: datetime = await _moment(uow, user_id, request.at, now, "started")
            await _clear_of_sessions(uow, user_id, moment)
            task.start(now)  # nothing else changes if it cannot start

            await uow.time_entries.add(
                TimeEntry(task_id=task.id, user_id=user_id, start_time=moment)
            )
            await uow.tasks.update(task)
            return TaskTimerOutputDTO(
                task=await _output(uow, task, user_id, now), started_at=moment
            )


class PauseTaskUseCase(UseCase[TimerRequest, TaskTimerOutputDTO]):
    """Stop working on a task for now: its timer stops (or is discarded)."""

    async def execute(self, request: TimerRequest) -> TaskTimerOutputDTO:
        """Pause the task, now or when ``at`` says; ``discard``: counting
        nothing.

        Raises:
            ValidationException: If the user ID or the prefix is invalid, or
                the moment is in the future or before the timer started.
            EntityNotFound: If the user has no such task.
            InvalidStateTransition: If its timer is not running.
        """
        user_id: UserId = UserId.from_string(
            request.user_id, error_msg="Invalid user ID."
        )
        now: datetime = self.clock.now()

        async with self.uow as uow:
            task: Task = await find_task(uow, request.task_id_prefix, user_id)
            running: list[TimeEntry] = await uow.time_entries.get_actives_for_task(
                task.id
            )
            if not running:
                raise InvalidStateTransition(
                    f"'{task.title}' has no timer running: nothing to pause."
                )
            moment: datetime = await _moment(uow, user_id, request.at, now, "paused")
            started: datetime = min(_aware(e.start_time) for e in running)
            if moment < started:
                raise ValidationException(
                    f"The timer of '{task.title}' started at "
                    f"{await _wall(uow, user_id, started)}: it cannot "
                    "stop before that."
                )
            minutes: int = sum(_until(e, moment) for e in running)
            task.pause(now, minutes, discarded=request.discard)
            for entry in running:
                if request.discard:
                    entry.discard(moment)
                else:
                    entry.stop(moment)
            await uow.time_entries.update_all(running)
            await uow.tasks.update(task)
            return TaskTimerOutputDTO(
                task=await _output(uow, task, user_id, now),
                session_minutes=minutes,
                stopped_at=moment,
                discarded=request.discard,
            )


async def _moment(
    uow: UnitOfWork,
    user_id: UserId,
    typed: DateInput | None,
    now: datetime,
    what: str,
) -> datetime:
    """Now, or the moment typed (never in the future)."""
    if typed is None:
        return now
    user: User | None = await uow.users.get_by_id(user_id)
    prefs: UserPrefs = prefs_of(uow, user)
    return past_moment(
        typed,
        now,
        prefs.timezone,
        needs_time=f"When it {what} needs a time of day, e.g. 'yesterday 23:10'.",
        in_future=f"A timer cannot be {what} in the future.",
    )


async def _clear_of_sessions(
    uow: UnitOfWork, user_id: UserId, moment: datetime
) -> None:
    """Refuse a start inside (or before) another session: from ``moment``
    to now no session may run — no time counts twice (a discarded one
    counts nowhere, so it does not stand in the way).

    Raises:
        ValidationException: Naming the session it would run over.
    """
    later: list[TimeEntry] = [
        e
        for e in await uow.time_entries.search(
            TimeEntryFilter(user_id=user_id, limit=100_000)
        )
        if e.end_time is not None
        and _aware(e.end_time) > moment
        and not e.discarded  # counted nowhere: nothing to count twice
    ]
    if not later:
        return
    clash: TimeEntry = min(later, key=lambda e: _aware(e.start_time))
    owner: Task | None = await uow.tasks.get_by_id(clash.task_id, user_id)
    assert clash.end_time is not None
    raise ValidationException(
        f"'{owner.title if owner else 'A deleted task'}' was timed from "
        f"{await _wall(uow, user_id, _aware(clash.start_time))} to "
        f"{await _wall(uow, user_id, _aware(clash.end_time))}: a "
        "timer started then would run over it — start it after that."
    )


async def _wall(uow: UnitOfWork, user_id: UserId, moment: datetime) -> str:
    """A moment as the user reads it: "2026-01-04 23:12" where they are."""
    user: User | None = await uow.users.get_by_id(user_id)
    prefs: UserPrefs = prefs_of(uow, user)
    try:
        zone: ZoneInfo = ZoneInfo(prefs.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo("UTC")
    return f"{moment.astimezone(zone):%Y-%m-%d %H:%M}"


def _until(entry: TimeEntry, moment: datetime) -> int:
    """A running session's minutes up to ``moment``."""
    return max(int((moment - _aware(entry.start_time)).total_seconds() // 60), 0)


def _aware(moment: datetime) -> datetime:
    """Naive instants (what SQLite hands back) are UTC."""
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


async def time_of(
    uow: UnitOfWork, task_id: TaskId, now: datetime
) -> tuple[int, datetime | None]:
    """A task's time: minutes spent so far, and since when a timer runs."""
    entries: list[TimeEntry] = await uow.time_entries.search(
        TimeEntryFilter(task_id=task_id, limit=10_000)
    )
    spent: int = sum(e.counted_minutes(now) for e in entries)
    running: list[datetime] = [e.start_time for e in entries if e.end_time is None]
    return spent, max(running) if running else None


async def _output(
    uow: UnitOfWork, task: Task, user_id: UserId, now: datetime
) -> TaskOutputDTO:
    spent, since = await time_of(uow, task.id, now)
    context = (
        await uow.contexts.get_by_id(task.context_id, user_id)
        if task.context_id
        else None
    )
    return TaskMapper.to_output(
        task, now, context=context, time_spent_minutes=spent, running_since=since
    )
