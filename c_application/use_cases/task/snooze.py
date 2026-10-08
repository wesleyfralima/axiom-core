"""`axpro task snooze`: put off what is due today, or late, to later.

By default to the next day at the same time (``business_day``: the next
business day); by some minutes from the later of now and the due date; or to
a moment typed (a time alone is today, a day keeps the task's time). Only a
task still open and due today or late; only later.

A recurring occurrence keeps its rule. It is refused when it would land on
its next occurrence's day, or after it (by time, not day, for a rule of
several times a day) — unless both are wanted (``keep_both``): then the
series moves on now (its next occurrence is made) and the snoozed one leaves
it as a one-off. A parent's subtasks follow it; a subtask stays within its
parent.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from a_core import DTO, UniqueId
from a_core.exceptions import ValidationException
from b_domain.entities import Task, User
from b_domain.entities.user import UserPrefs
from b_domain.exceptions.snooze import SnoozeRefusal, SnoozeRefusedError
from b_domain.ports.unit_of_work import UnitOfWork
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import UserId
from b_domain.value_objects.dates import DueDate
from c_application.dtos.task_dtos import TaskOutputDTO
from c_application.mappers.task_mapper import TaskMapper
from c_application.use_cases.task.relations import (
    add_occurrence,
    bring_subtasks,
    due_text,
    fit_under,
    pull_subtasks,
)
from c_application.utils import format_task_recurrence
from c_application.utils.date_input import DateInput, local_today, resolve_date_input
from c_application.utils.task_utils import find_task
from c_application.utils.work_calendar import load_work_calendar, use_work_calendar

# How far to look for the next business day (a long holiday season included)
_BUSINESS_DAYS_AHEAD: int = 60


@dataclass(frozen=True, kw_only=True)
class SnoozeTaskRequest(DTO):
    """Snooze one task: to the next day (the default), the next business
    day, by some minutes, or to a moment typed — one of them."""

    user_id: str
    # Its ID or an ID prefix
    task_id_prefix: str
    # A moment as typed ("15:00" is today; "tomorrow", a date: at its time)
    to: DateInput | None = None
    # How long to put it off, from the later of now and its due date
    minutes: int | None = None
    # The next business day instead of the next day
    business_day: bool = False
    # A recurring occurrence landing on its next one: keep both
    keep_both: bool = False


@dataclass(frozen=True, kw_only=True)
class SnoozedTaskOutputDTO(DTO):
    """The task snoozed, and its series' next occurrence when it was made now
    (both kept)."""

    task: TaskOutputDTO
    next: TaskOutputDTO | None = None
    # What the snooze did on its own (subtasks moved along)
    notes: list[str] = field(default_factory=list)


class SnoozeTaskUseCase(UseCase[SnoozeTaskRequest, SnoozedTaskOutputDTO]):
    """Put a task off to later, by the rules above."""

    async def execute(self, request: SnoozeTaskRequest) -> SnoozedTaskOutputDTO:
        """Snooze the task.

        Raises:
            ValidationException: If the user ID is invalid, more than one way
                of saying when is given, the minutes are not positive, or a
                subtask would go past its parent.
            InvalidValueError: If ``to`` is not a date the user can type.
            SnoozeRefusedError: If the task cannot be snoozed (closed, no due
                date, due after today), the moment is not later, or it lands
                on the next occurrence without ``keep_both``.
            EntityNotFound: If no task matches the ID.
        """
        user_id: UserId = UserId.from_string(
            request.user_id, error_msg="Invalid user ID."
        )
        given: int = sum(
            [request.to is not None, request.minutes is not None, request.business_day]
        )
        if given > 1:
            raise ValidationException(
                "Say when once: a moment, a time to wait, or the next business day."
            )
        if request.minutes is not None and request.minutes <= 0:
            raise ValidationException("Snooze for some time: more than 0 minutes.")
        now: datetime = self.clock.now()
        moment_now: datetime = now if now.tzinfo else now.replace(tzinfo=UTC)

        async with self.uow as uow:
            task: Task = await find_task(uow, request.task_id_prefix, user_id)
            user: User | None = await uow.users.get_by_id(user_id)
            prefs: UserPrefs = user.preferences if user else UserPrefs()
            zone: ZoneInfo = _zone(prefs.timezone)
            today: date = local_today(now, prefs.timezone)
            await use_work_calendar(uow, user_id, prefs, [task])

            due: DueDate = _snoozable(task, today, zone)
            target: DueDate = await self._target(
                uow, request, task, due, user_id, prefs, today, zone, moment_now
            )
            if target.materialize() <= max(due.materialize(), moment_now):
                later_of: str = (
                    "now" if moment_now >= due.materialize() else _moment(due, zone)
                )
                raise SnoozeRefusedError(
                    SnoozeRefusal.NOT_LATER,
                    f"A snooze only puts a task off: {_moment(target, zone)} is "
                    f"not after {later_of}.",
                )

            # A recurring occurrence: not onto its next one, unless both stay
            keep_both: bool = False
            if task.recurrence is not None and task.parent_id is None:
                upcoming: Task | None = task.create_next_occurrence(now)
                if upcoming is not None and upcoming.due_date is not None:
                    following: DueDate = upcoming.due_date
                    lands: bool = (
                        target.materialize() >= following.materialize()
                        if task.recurrence.is_sub_daily
                        else _wall(target, zone).date() >= _wall(following, zone).date()
                    )
                    if lands and not request.keep_both:
                        raise SnoozeRefusedError(
                            SnoozeRefusal.LANDS_ON_NEXT,
                            f"The next '{task.title}' is {_moment(following, zone)}: "
                            "this one would land on it.",
                            next_due=following.value,
                        )
                    keep_both = lands

            old_due: DueDate = due
            changes: dict[str, tuple[str | None, str | None]] = {
                "due": (due_text(old_due), due_text(target))
            }
            if keep_both:
                changes["recurrence"] = (
                    format_task_recurrence(task.recurrence),
                    None,
                )
            made: Task | None = task.snooze(now, target, keep_both, changes)
            parent: Task | None = (
                await uow.tasks.get_by_id(task.parent_id, user_id)
                if task.parent_id
                else None
            )
            notes: list[str] = []
            if parent is not None:
                # A subtask stays within its parent: past it is refused
                notes += fit_under(
                    now, task, parent, due_asked=True, priority_asked=False
                )
            await uow.tasks.update(task)
            snooze_id: UniqueId = task.peek_events()[-1].id

            following_task: Task | None = None
            if made is not None:
                following_task = await add_occurrence(uow, made)
                if following_task is not None:
                    await bring_subtasks(
                        uow,
                        task,
                        following_task,
                        now,
                        caused_by=snooze_id,
                        parent_due=old_due,
                    )
            if parent is None:
                notes += await pull_subtasks(uow, now, task, old_due, snooze_id)

            context = (
                await uow.contexts.get_by_id(task.context_id, user_id)
                if task.context_id
                else None
            )
            return SnoozedTaskOutputDTO(
                task=TaskMapper.to_output(task, now, context=context, parent=parent),
                next=(
                    TaskMapper.to_output(following_task, now, context=context)
                    if following_task is not None
                    else None
                ),
                notes=notes,
            )

    async def _target(
        self,
        uow: UnitOfWork,
        request: SnoozeTaskRequest,
        task: Task,
        due: DueDate,
        user_id: UserId,
        prefs: UserPrefs,
        today: date,
        zone: ZoneInfo,
        moment_now: datetime,
    ) -> DueDate:
        """Where the task goes, in its due date's own kind (floating or
        fixed) and zone."""
        wall: datetime = _wall(due, zone)
        if request.minutes is not None:
            start: datetime = max(due.materialize(), moment_now)
            return _due_at(start + timedelta(minutes=request.minutes), due, zone)
        if request.to is not None:
            typed: date | datetime = resolve_date_input(request.to, today=today)
            if not isinstance(typed, datetime):
                typed = datetime.combine(typed, wall.time())
            return _due_from_wall(typed, due, zone)
        day: date = today + timedelta(days=1)
        if request.business_day:
            calendar = await load_work_calendar(uow, user_id, prefs)
            for _ in range(_BUSINESS_DAYS_AHEAD):
                if calendar.is_business_day(day):
                    break
                day += timedelta(days=1)
        return _due_from_wall(datetime.combine(day, wall.time()), due, zone)


def _snoozable(task: Task, today: date, zone: ZoneInfo) -> DueDate:
    """The task's due date, when it can be snoozed: open, and due today or
    late.

    Raises:
        SnoozeRefusedError: If it cannot.
    """
    if task.status.is_closed:
        raise SnoozeRefusedError(
            SnoozeRefusal.CLOSED,
            f"'{task.title}' is {task.status}: only an open task can be snoozed.",
        )
    if task.due_date is None:
        raise SnoozeRefusedError(
            SnoozeRefusal.NO_DUE,
            f"'{task.title}' has no due date: there is nothing to put off.",
        )
    if _wall(task.due_date, zone).date() > today:
        raise SnoozeRefusedError(
            SnoozeRefusal.NOT_DUE_YET,
            f"'{task.title}' is due {_moment(task.due_date, zone)}, after today: "
            "a snooze puts off what is due today, or late.",
        )
    return task.due_date


def _zone(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _wall(due: DueDate, zone: ZoneInfo) -> datetime:
    """A due date as wall-clock time (naive): a floating one as it is, a
    fixed one where the user is."""
    if due.is_floating:
        return due.value
    return due.value.astimezone(zone).replace(tzinfo=None)


def _due_from_wall(wall: datetime, like: DueDate, zone: ZoneInfo) -> DueDate:
    """A wall-clock time as a due date of ``like``'s kind: floating in its
    own zone, or fixed, read where the user is."""
    if like.is_floating:
        return DueDate.floating(wall, like.timezone or "UTC")
    return DueDate.fixed(wall.replace(tzinfo=zone))


def _due_at(moment: datetime, like: DueDate, zone: ZoneInfo) -> DueDate:
    """An instant as a due date of ``like``'s kind."""
    if like.is_floating:
        own: ZoneInfo = _zone(like.timezone or "UTC")
        return DueDate.floating(
            moment.astimezone(own).replace(tzinfo=None), like.timezone or "UTC"
        )
    return DueDate.fixed(moment.astimezone(UTC))


def _moment(due: DueDate, zone: ZoneInfo) -> str:
    """A due date in a message, where the user is: "Wed Oct 14 07:00"."""
    return _wall(due, zone).strftime("%a %b %d %H:%M")
