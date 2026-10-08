"""`axpro today`: the day at a glance — late, due today, done today, next.

Every context by default: the day is one, whatever context is active (an
overdue bill at home shows during work hours). Recurring tasks show as the
occurrence that exists; nothing is projected.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from a_core import DTO
from b_domain.entities import Context, Task, User
from b_domain.entities.user import UserPrefs
from b_domain.ports.repositories.filters import TaskFilter
from b_domain.ports.unit_of_work import UnitOfWork
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import ContextId, TaskId, TaskStatus, UserId
from c_application.dtos.context_dtos import ContextOutputDTO
from c_application.dtos.task_dtos import DayLoadDTO, TaskOutputDTO
from c_application.mappers.context_mapper import ContextMapper
from c_application.mappers.task_mapper import TaskMapper
from c_application.use_cases.task.capacity import day_load
from c_application.use_cases.task.radar import RadarDTO, radar_of
from c_application.utils import find_context
from c_application.utils.date_input import local_today
from c_application.utils.work_calendar import use_work_calendar


@dataclass(frozen=True, kw_only=True)
class TodayRequest(DTO):
    """The day of one user; ``context_id`` (a name or ID prefix) limits it."""

    user_id: str
    context_id: str | None = None
    # How many tasks after today to show
    next_count: int = 3


@dataclass(frozen=True, kw_only=True)
class TodayOutputDTO(DTO):
    """The day: each list in the order it is read.

    ``overdue`` are the open tasks already late (by their deadline), oldest
    first; ``today`` the open ones due today and not late yet; ``done`` the
    ones completed today, in the order they were; ``next`` the first open
    ones after today (a subtask due with its parent is left to it).
    """

    day: date
    overdue: list[TaskOutputDTO] = field(default_factory=list)
    today: list[TaskOutputDTO] = field(default_factory=list)
    done: list[TaskOutputDTO] = field(default_factory=list)
    next: list[TaskOutputDTO] = field(default_factory=list)
    # The context the day is limited to (None: every context)
    context: ContextOutputDTO | None = None
    # Late and today's tasks the radar flags (put off, or missed in a row);
    # none when the user turned the warnings off
    radar: list[RadarDTO] = field(default_factory=list)
    # How full today is: the open tasks' estimates against what is left
    load: DayLoadDTO | None = None
    # Whether to warn about it (the user's full_day_warnings)
    warn_full: bool = True


@dataclass(kw_only=True)
class Day:
    """The user's day, as tasks: what ``today`` and ``wrap`` are built from.

    ``overdue`` and ``due_today`` are open tasks, by due date; ``later`` the
    open ones after today, by due date (a subtask due with its parent left
    to it); ``done`` those completed today, in that order.
    """

    now: datetime
    today: date
    zone: ZoneInfo
    prefs: UserPrefs
    scope: Context | None
    overdue: list[Task] = field(default_factory=list)
    due_today: list[Task] = field(default_factory=list)
    later: list[Task] = field(default_factory=list)
    done: list[Task] = field(default_factory=list)
    parents: dict[TaskId, Task] = field(default_factory=dict)
    contexts: dict[ContextId, Context] = field(default_factory=dict)

    def output(self, task: Task) -> TaskOutputDTO:
        """A task as the lists show it: its context, its parent's title."""
        parent: Task | None = (
            self.parents.get(task.parent_id) if task.parent_id else None
        )
        return TaskMapper.to_output(
            task,
            self.now,
            context=self.contexts.get(task.context_id) if task.context_id else None,
            parent_title=str(parent.title) if parent else None,
            parent=parent,
        )

    def wall(self, task: Task) -> datetime:
        """A task's due date as wall-clock time where the user is."""
        assert task.due_date is not None
        return _wall_clock(task.due_date.value, self.zone)

    def due_with_parent(self, task: Task) -> bool:
        """A subtask due when its parent is: the parent stands for it."""
        return _due_with_parent(task, self.parents)

    def context_output(self) -> ContextOutputDTO | None:
        """The context the day is limited to, if any."""
        if self.scope is None:
            return None
        return ContextMapper.to_output(
            self.scope, ContextOutputDTO, self.prefs.active_context_id
        )


async def collect_day(
    uow: UnitOfWork, user_id: UserId, now: datetime, context_ref: str | None
) -> Day:
    """The user's day: the open tasks with a due date, sorted into late, due
    today and later, and what was completed today (by ``completed_at``: one
    done "yesterday 21:00" this morning is yesterday's). Every context unless
    ``context_ref`` (a name or ID prefix) names one.

    Raises:
        EntityNotFound: If the context matches no context.
        AmbiguousIdentifierError: If the context's ID prefix matches several.
    """
    user: User | None = await uow.users.get_by_id(user_id)
    prefs: UserPrefs = user.preferences if user else UserPrefs()
    zone: ZoneInfo = _zone(prefs.timezone)
    today: date = local_today(now, prefs.timezone)
    start: datetime = datetime.combine(today, time(), tzinfo=zone)
    end: datetime = start + timedelta(days=1)

    contexts: list[Context] = await uow.contexts.list_by_user(user_id)
    scope: Context | None = find_context(contexts, context_ref) if context_ref else None
    context_id: ContextId | None = scope.id if scope else None

    open_tasks: list[Task] = await uow.tasks.list(
        TaskFilter(
            user_id=user_id,
            exclude_statuses=TaskStatus.closed(),
            has_due_date=True,
            context_id=context_id,
            limit=10_000,
        )
    )
    # Touched today, then by when it was completed
    done_tasks: list[Task] = [
        t
        for t in await uow.tasks.list(
            TaskFilter(
                user_id=user_id,
                status=TaskStatus.DONE,
                context_id=context_id,
                updated_after=start.astimezone(UTC),
                limit=10_000,
            )
        )
        if t.completed_at is not None and start <= _aware(t.completed_at) < end
    ]
    await use_work_calendar(uow, user_id, prefs, open_tasks)

    day: Day = Day(
        now=now,
        today=today,
        zone=zone,
        prefs=prefs,
        scope=scope,
        contexts={c.id: c for c in contexts},
    )
    for ref in {t.parent_id for t in open_tasks + done_tasks if t.parent_id}:
        parent: Task | None = await uow.tasks.get_by_id(ref, user_id)
        if parent is not None:
            day.parents[ref] = parent

    for task in sorted(
        open_tasks, key=lambda t: (day.wall(t), t.parent_id is not None)
    ):
        wall: datetime = day.wall(task)
        parent = day.parents.get(task.parent_id) if task.parent_id else None
        if task.is_overdue(now, parent) or wall.date() < today:
            day.overdue.append(task)
        elif wall.date() == today:
            day.due_today.append(task)
        elif not day.due_with_parent(task):
            day.later.append(task)
    day.done = sorted(done_tasks, key=lambda t: _aware(t.completed_at))
    return day


class TodayUseCase(UseCase[TodayRequest, TodayOutputDTO]):
    """Build the user's day from the open tasks and today's completions."""

    async def execute(self, request: TodayRequest) -> TodayOutputDTO:
        """Build the day.

        Raises:
            ValidationException: If the user ID is invalid.
            EntityNotFound: If the context matches no context.
            AmbiguousIdentifierError: If the context's ID prefix matches several.
        """
        user_id: UserId = UserId.from_string(
            request.user_id, error_msg="Invalid user ID."
        )
        async with self.uow as uow:
            day: Day = await collect_day(
                uow, user_id, self.clock.now(), request.context_id
            )
            flagged: dict[TaskId, RadarDTO] = await radar_of(
                uow,
                user_id,
                day.prefs,
                day.overdue + day.due_today,
                day.today,
                day.zone,
            )
            return TodayOutputDTO(
                load=await day_load(
                    uow, user_id, day.prefs, day.today, self.clock.now()
                ),
                warn_full=day.prefs.full_day_warnings,
                radar=list(flagged.values()),
                day=day.today,
                overdue=[day.output(t) for t in day.overdue],
                today=[day.output(t) for t in day.due_today],
                done=[day.output(t) for t in day.done],
                next=[day.output(t) for t in day.later[: max(request.next_count, 0)]],
                context=day.context_output(),
            )


def _due_with_parent(task: Task, parents: dict[TaskId, Task]) -> bool:
    """A subtask due when its parent is: the parent stands for it."""
    parent: Task | None = parents.get(task.parent_id) if task.parent_id else None
    return (
        parent is not None
        and not parent.status.is_closed
        and parent.due_date is not None
        and task.due_date is not None
        and parent.due_date.value == task.due_date.value
    )


def _zone(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _aware(moment: datetime | None) -> datetime:
    """An instant as aware (naive values are UTC)."""
    assert moment is not None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _wall_clock(dt: datetime, zone: ZoneInfo) -> datetime:
    """A due date as wall-clock time where the user is (naive); a floating
    one already is."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(zone).replace(tzinfo=None)
