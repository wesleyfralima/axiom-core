"""`axpro wrap`: the end of the day — what was done, and what is left.

Nothing is kept between runs: what is left is what is open and due today, or
late, right now. Each task says what can be done with it (``actions``) — the
interface asks, and does it with the use cases that already exist (snooze,
cancel, complete, edit). A subtask due with its parent goes with it, so it is
not asked about. When nothing is left, a few tasks ahead to get done now:
the shortest first.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import StrEnum

from a_core import DTO
from b_domain.entities import Task
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import TaskId, UserId
from c_application.dtos.context_dtos import ContextOutputDTO
from c_application.dtos.task_dtos import TaskOutputDTO
from c_application.use_cases.task.radar import RadarDTO, radar_of
from c_application.use_cases.task.today import Day, collect_day
from c_application.utils.date_input import resolve_horizon


class WrapAction(StrEnum):
    """What can be done with a task left at the end of the day."""

    TOMORROW = "tomorrow"  # snooze to the next day
    BUSINESS_DAY = "business_day"  # snooze to the next business day
    DATE = "date"  # snooze to a moment typed
    REMOVE_DATE = "remove_date"  # no due date any more
    SKIP = "skip"  # a recurring one: cancel this occurrence
    CANCEL = "cancel"  # not to be done
    DONE = "done"
    SPLIT = "split"  # the radar flags it: into subtasks, smaller steps
    KEEP = "keep"  # leave it as it is


@dataclass(frozen=True, kw_only=True)
class WrapRequest(DTO):
    """The end of one user's day; ``context_id`` (a name or ID prefix)
    limits it."""

    user_id: str
    context_id: str | None = None
    # How many tasks ahead to offer when nothing is left
    ahead_count: int = 5


@dataclass(frozen=True, kw_only=True)
class WrapItemDTO(DTO):
    """A task left, and what can be done with it, in the order to offer."""

    task: TaskOutputDTO
    actions: list[WrapAction]
    # The radar flags it: put off, or missed in a row (a decision is due)
    radar: RadarDTO | None = None


@dataclass(frozen=True, kw_only=True)
class WrapOutputDTO(DTO):
    """The end of the day.

    ``done``: completed today, in that order. ``left``: open and due today,
    or late, oldest first. ``ahead``: only when nothing is left — open tasks
    due in the next days (the ``days_ahead`` preference) that can be done
    now, the shortest estimate first.
    """

    day: date
    done: list[TaskOutputDTO] = field(default_factory=list)
    left: list[WrapItemDTO] = field(default_factory=list)
    ahead: list[TaskOutputDTO] = field(default_factory=list)
    context: ContextOutputDTO | None = None


class WrapUseCase(UseCase[WrapRequest, WrapOutputDTO]):
    """Build the end of the user's day."""

    async def execute(self, request: WrapRequest) -> WrapOutputDTO:
        """Build it.

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
            day: Day = await collect_day(uow, user_id, now, request.context_id)

            pending: list[Task] = day.overdue + day.due_today
            asked: set[TaskId] = {t.id for t in pending}
            # Its parent is asked about, and takes it along
            pending = [
                t
                for t in pending
                if not (day.due_with_parent(t) and t.parent_id in asked)
            ]
            flagged: dict[TaskId, RadarDTO] = await radar_of(
                uow, user_id, day.prefs, pending, day.today, day.zone
            )
            left: list[WrapItemDTO] = [
                WrapItemDTO(
                    task=day.output(t),
                    actions=_actions(t, day, t.id in flagged),
                    radar=flagged.get(t.id),
                )
                for t in pending
            ]

            ahead: list[Task] = []
            if not left:
                horizon: date = resolve_horizon(day.prefs.days_ahead, today=day.today)
                ahead = sorted(
                    (
                        t
                        for t in day.later
                        if day.wall(t).date() <= horizon and not t.is_blocked
                    ),
                    key=lambda t: (t.estimated_duration_minutes, day.wall(t)),
                )[: max(request.ahead_count, 0)]

            return WrapOutputDTO(
                day=day.today,
                done=[day.output(t) for t in day.done],
                left=left,
                ahead=[day.output(t) for t in ahead],
                context=day.context_output(),
            )


def _actions(task: Task, day: Day, flagged: bool = False) -> list[WrapAction]:
    """What fits a task left: a recurring one is skipped, not cancelled, and
    keeps its date (its rule needs one); a subtask keeps a date too, and
    goes no later than its parent; a waiting one cannot be done; one the
    radar flags can be split into subtasks (not a subtask: one level)."""
    actions: list[WrapAction] = []
    if _fits_tomorrow(task, day):
        actions += [WrapAction.TOMORROW, WrapAction.BUSINESS_DAY]
    actions.append(WrapAction.DATE)
    repeats: bool = task.recurrence is not None and task.parent_id is None
    if not repeats and task.parent_id is None:
        actions.append(WrapAction.REMOVE_DATE)
    actions.append(WrapAction.SKIP if repeats else WrapAction.CANCEL)
    if not task.is_blocked:
        actions.append(WrapAction.DONE)
    if flagged and task.parent_id is None:
        actions.append(WrapAction.SPLIT)
    actions.append(WrapAction.KEEP)
    return actions


def _fits_tomorrow(task: Task, day: Day) -> bool:
    """Whether the next day, at its time, is a place the snooze takes it to:
    not onto a recurring one's next occurrence, not past a subtask's parent."""
    tomorrow: date = day.today + timedelta(days=1)
    target: datetime = datetime.combine(tomorrow, day.wall(task).time())
    if task.recurrence is not None and task.parent_id is None:
        if task.recurrence.keep_missed:
            return True  # the next one waits for this one
        upcoming: Task | None = task.create_next_occurrence(day.now)
        if upcoming is not None and upcoming.due_date is not None:
            return day.wall(upcoming).date() > tomorrow
        return True
    parent: Task | None = day.parents.get(task.parent_id) if task.parent_id else None
    if parent is not None and parent.due_date is not None:
        return target <= day.wall(parent)
    return True
