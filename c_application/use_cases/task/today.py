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
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import ContextId, TaskId, TaskStatus, UserId
from c_application.dtos.context_dtos import ContextOutputDTO
from c_application.dtos.task_dtos import TaskOutputDTO
from c_application.mappers.context_mapper import ContextMapper
from c_application.mappers.task_mapper import TaskMapper
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
        now: datetime = self.clock.now()

        async with self.uow as uow:
            user: User | None = await uow.users.get_by_id(user_id)
            prefs: UserPrefs = user.preferences if user else UserPrefs()
            zone: ZoneInfo = _zone(prefs.timezone)
            today: date = local_today(now, prefs.timezone)
            start: datetime = datetime.combine(today, time(), tzinfo=zone)
            end: datetime = start + timedelta(days=1)

            contexts: list[Context] = await uow.contexts.list_by_user(user_id)
            scope: Context | None = (
                find_context(contexts, request.context_id)
                if request.context_id
                else None
            )
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
            # Done today: touched today, then by when it was completed (a
            # task done "yesterday 21:00" this morning is yesterday's)
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

            by_id: dict[ContextId, Context] = {c.id: c for c in contexts}
            parents: dict[TaskId, Task] = {}
            for ref in {
                t.parent_id for t in open_tasks + done_tasks if t.parent_id is not None
            }:
                parent: Task | None = await uow.tasks.get_by_id(ref, user_id)
                if parent is not None:
                    parents[ref] = parent

            def output(task: Task) -> TaskOutputDTO:
                parent: Task | None = (
                    parents.get(task.parent_id) if task.parent_id else None
                )
                return TaskMapper.to_output(
                    task,
                    now,
                    context=by_id.get(task.context_id) if task.context_id else None,
                    parent_title=str(parent.title) if parent else None,
                    parent=parent,
                )

            overdue: list[tuple[datetime, TaskOutputDTO]] = []
            due_today: list[tuple[datetime, TaskOutputDTO]] = []
            later: list[tuple[datetime, TaskOutputDTO]] = []
            for task in open_tasks:
                dto: TaskOutputDTO = output(task)
                assert dto.due_date is not None  # has_due_date
                wall: datetime = _wall_clock(dto.due_date, zone)
                if dto.is_overdue or wall.date() < today:
                    overdue.append((wall, dto))
                elif wall.date() == today:
                    due_today.append((wall, dto))
                elif not _due_with_parent(task, parents):
                    later.append((wall, dto))

            done: list[TaskOutputDTO] = [
                output(t)
                for t in sorted(done_tasks, key=lambda t: _aware(t.completed_at))
            ]
            return TodayOutputDTO(
                day=today,
                overdue=_by_date(overdue),
                today=_by_date(due_today),
                done=done,
                next=_by_date(later)[: max(request.next_count, 0)],
                context=(
                    ContextMapper.to_output(
                        scope, ContextOutputDTO, prefs.active_context_id
                    )
                    if scope
                    else None
                ),
            )


def _by_date(pairs: list[tuple[datetime, TaskOutputDTO]]) -> list[TaskOutputDTO]:
    """The tasks by due date; a parent before the subtasks due with it."""
    pairs.sort(key=lambda pair: (pair[0], pair[1].parent_id is not None))
    return [dto for _, dto in pairs]


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
