"""`axpro report`: what was done in a period, from the history and the tasks.

Nothing new is collected. **Each task counts once, by how it ended**: its
last closing in the history (done or cancelled — not undone, not followed
by a reopen), when it falls in the period; a deleted task never counts. A
completion is on time or late against the deadline the task had *when it
was completed* (the snapshot in its history entry: due + estimate, or the
due date when strict), so moving a date later does not rewrite the past.

**A series is judged by its slots** (``series_slots``): the days its rule
says should have had an occurrence, each with one outcome — done on time,
late, skipped, missed (nothing recorded, its day gone) or pending (today).
Hourly series are apart (``HourlySeriesDTO``): how many of the day's slots
were done.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from a_core import DTO
from a_core.exceptions import ValidationException
from b_domain.entities import Task, TimeEntry, User
from b_domain.entities.user import UserPrefs
from b_domain.ports.repositories.filters import TaskFilter, TimeEntryFilter
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import ContextId, Priority, TaskId, TaskStatus, UserId
from b_domain.value_objects.dates import deadline_of
from b_domain.value_objects.recurrences._serial import axiom_date_from_dict
from b_domain.value_objects.task_history import TaskAction, TaskHistoryEntry
from c_application.use_cases.task.series_slots import (
    LATE,
    MISSED,
    NO_SLOT,
    ON_TIME,
    PENDING,
    SKIPPED,
    Slot,
    series_slots,
    streak_of,
)
from c_application.use_cases.task.timer import time_of
from c_application.utils import format_task_recurrence
from c_application.utils.date_input import DateInput, local_today, resolve_date_input
from c_application.utils.prefs import prefs_of
from c_application.utils.recurrence_input import WEEK_STARTS
from c_application.utils.work_calendar import use_work_calendar

_NO_CONTEXT: str = "none"
_GONE_CONTEXT: str = "(deleted context)"

_CLOSINGS: tuple[TaskAction, ...] = (TaskAction.COMPLETED, TaskAction.CANCELLED)


@dataclass(frozen=True, kw_only=True)
class ReportRequest(DTO):
    """The period to report on.

    ``period``: "week" (this week, from the user's week_start), "month" (this
    month); otherwise ``start``/``end`` (dates as typed; ``end`` defaults to
    today and never goes past it); with none of them, the last 7 days.
    """

    user_id: str
    period: str | None = None
    start: DateInput | None = None
    end: DateInput | None = None


@dataclass(frozen=True, kw_only=True)
class CountDTO(DTO):
    """How many, for one label (a context, a priority)."""

    label: str
    count: int


@dataclass(frozen=True, kw_only=True)
class DayDTO(DTO):
    """One day of the period."""

    day: date
    done: int
    created: int


@dataclass(frozen=True, kw_only=True)
class SeriesReportDTO(DTO):
    """One recurring series (not hourly), judged by its slots.

    Attributes:
        series_id (str): The series.
        task_id (str): Its latest occurrence (what to open).
        title (str): Its latest occurrence's title.
        rule (str | None): How it repeats now (None: it stopped).
        done (int): Slots of the period done (on time or late).
        skipped (int): Slots skipped (cancelled).
        missed (int): Slots gone by with nothing recorded.
        pending (int): Today's slot, not done yet (0 or 1).
        streak (int): The current streak: slots done in a row, up to the
            latest one gone by (not limited to the period; today's, still
            pending, does not break it).
        rate (float | None): Done ÷ (done + skipped + missed) in the period
            (None when none of them happened).
        timeline (list[str]): One entry per day of the period: "none" (no
            slot that day), "on_time", "late", "skipped", "missed" or
            "pending". An occurrence is on its slot's day, whenever it was
            closed.
    """

    series_id: str
    task_id: str
    title: str
    rule: str | None
    done: int
    skipped: int
    missed: int
    streak: int
    rate: float | None
    pending: int = 0
    timeline: list[str] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class HourlyDayDTO(DTO):
    """One day of an hourly series: its slots done of those due (today, up
    to now)."""

    day: date
    done: int
    slots: int


@dataclass(frozen=True, kw_only=True)
class HourlySeriesDTO(DTO):
    """A series that repeats within the day, apart from the others: how many
    of its slots were done.

    Attributes:
        series_id (str): The series.
        task_id (str): Its latest occurrence (what to open).
        title (str): Its latest occurrence's title.
        rule (str | None): How it repeats now (None: it stopped).
        done (int): Slots of the period done.
        slots (int): Slots of the period due (today: up to now).
        rate (float | None): Done ÷ slots (None with no slot).
        days (list[HourlyDayDTO]): Each day of the period.
    """

    series_id: str
    task_id: str
    title: str
    rule: str | None
    done: int
    slots: int
    rate: float | None
    days: list[HourlyDayDTO] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class AccuracyDTO(DTO):
    """Estimated vs. actual for the tasks done with measured time.

    ``label`` is a context name, or "all" for every one of them.
    """

    label: str
    tasks: int
    estimated_minutes: int
    actual_minutes: int


@dataclass(frozen=True, kw_only=True)
class ReportOutputDTO(DTO):
    """What happened in the period (``start`` to ``end``, both included)."""

    start: date
    end: date
    period: str
    done: int = 0
    created: int = 0
    cancelled: int = 0
    on_time: int = 0
    late: int = 0
    no_due: int = 0
    days: list[DayDTO] = field(default_factory=list)
    by_context: list[CountDTO] = field(default_factory=list)
    by_priority: list[CountDTO] = field(default_factory=list)
    series: list[SeriesReportDTO] = field(default_factory=list)
    # Series that repeat within the day, counted apart
    hourly: list[HourlySeriesDTO] = field(default_factory=list)
    # Series still going with no slot in the period (not listed)
    quiet_series: int = 0
    # Time measured by timers inside the period (the part of each session in
    # it), in all and by context
    time_spent_minutes: int = 0
    time_by_context: list[CountDTO] = field(default_factory=list)
    # Estimated vs. actual of the tasks done in the period with measured time
    accuracy: list[AccuracyDTO] = field(default_factory=list)
    # When completions happen most (hours "09:00"), from 5 completions on
    best_hours: list[CountDTO] = field(default_factory=list)


class ReportUseCase(UseCase[ReportRequest, ReportOutputDTO]):
    """What was done in a period: counts, days, contexts, priorities, series."""

    async def execute(self, request: ReportRequest) -> ReportOutputDTO:
        """Build the report.

        Raises:
            ValidationException: If the user ID is invalid, the period is
                unknown, or it ends before it starts.
            InvalidValueError: If a date is not one the user can type.
        """
        user_id: UserId = UserId.from_string(
            request.user_id, error_msg="Invalid user ID."
        )
        now: datetime = self.clock.now()

        async with self.uow as uow:
            user: User | None = await uow.users.get_by_id(user_id)
            prefs: UserPrefs = prefs_of(uow, user)
            zone: ZoneInfo = _zone(prefs.timezone)
            today: date = local_today(now, prefs.timezone)
            first, last, label = _period(request, today, prefs)

            start: datetime = datetime.combine(first, time(), tzinfo=zone)
            end: datetime = datetime.combine(
                last + timedelta(days=1), time(), tzinfo=zone
            )
            # Up to now as well: an undo or a reopen after the period still
            # changes how a task ended
            alive: list[TaskHistoryEntry] = _alive(
                await uow.task_history.between(
                    user_id, start, max(end, now + timedelta(days=1))
                )
            )
            # Each task once: its last closing, when it is in the period
            ended: list[TaskHistoryEntry] = [
                e
                for e in _last_closings(alive).values()
                if start <= _aware(e.occurred_at) < end
            ]
            creations: list[TaskHistoryEntry] = [
                e
                for e in alive
                if e.action == TaskAction.CREATED
                and start <= _aware(e.occurred_at) < end
            ]
            touched: set[TaskId] = {e.task_id for e in ended + creations}
            tasks: dict[TaskId, Task] = (
                {
                    t.id: t
                    for t in await uow.tasks.list(
                        TaskFilter(
                            user_id=user_id,
                            ids=list(touched),
                            deleted=None,
                            limit=10_000,
                        )
                    )
                }
                if touched
                else {}
            )
            # A deleted task never counts (the sync's copies the user removed)
            ended = [e for e in ended if _counts_for(tasks.get(e.task_id))]
            creations = [e for e in creations if _counts_for(tasks.get(e.task_id))]
            completions = [e for e in ended if e.action == TaskAction.COMPLETED]
            # A subtask due with its parent shares its parent's deadline
            parent_ids: set[TaskId] = {
                TaskId.from_string(ref)
                for e in completions
                if (
                    ref := (e.previous or _state_of(tasks.get(e.task_id))).get(
                        "parent_id"
                    )
                )
            }
            parents: dict[TaskId, Task] = (
                {
                    t.id: t
                    for t in await uow.tasks.list(
                        TaskFilter(
                            user_id=user_id,
                            ids=list(parent_ids),
                            deleted=None,
                            limit=10_000,
                        )
                    )
                }
                if parent_ids
                else {}
            )
            contexts: dict[ContextId, str] = {
                c.id: c.name for c in await uow.contexts.list_by_user(user_id)
            }

            # The series, by their slots (read while the unit of work is
            # open: floating dates are read where the user is)
            in_series: list[Task] = await uow.tasks.list(
                TaskFilter(user_id=user_id, in_series=True, limit=10_000)
            )
            await use_work_calendar(uow, user_id, prefs, in_series)
            histories: list[TaskHistoryEntry] = (
                _alive(
                    await uow.task_history.list_for_tasks(
                        [t.id for t in in_series], user_id
                    )
                )
                if in_series
                else []
            )
            series, hourly, quiet = _series(
                in_series,
                _last_closings(histories),
                _days(first, last),
                today,
                zone,
                now,
            )

            # Sessions that touch the period (one can start the day before)
            sessions: list[TimeEntry] = [
                e
                for e in await uow.time_entries.search(
                    TimeEntryFilter(
                        user_id=user_id,
                        started_after=start - timedelta(days=1),
                        started_before=end,
                        limit=100_000,
                    )
                )
                if _aware(e.end_time or now) > start and not e.discarded
            ]
            session_tasks: dict[TaskId, Task] = (
                {
                    t.id: t
                    for t in await uow.tasks.list(
                        TaskFilter(
                            user_id=user_id,
                            ids=list({e.task_id for e in sessions}),
                            deleted=None,
                            limit=10_000,
                        )
                    )
                }
                if sessions
                else {}
            )
            spent_on: dict[TaskId, int] = {}
            for entry in completions:
                if entry.task_id not in spent_on:
                    spent_on[entry.task_id], _ = await time_of(uow, entry.task_id, now)

        on_time = late = no_due = 0
        by_context: Counter[str] = Counter()
        by_priority: Counter[str] = Counter()
        for entry in completions:
            state: dict[str, Any] = entry.previous or _state_of(
                tasks.get(entry.task_id)
            )
            if _deadline(state, parents) is None:
                no_due += 1
            elif _punctuality(entry, tasks.get(entry.task_id), parents) == ON_TIME:
                on_time += 1
            else:
                late += 1
            by_context[_context_name(state, contexts)] += 1
            if state.get("priority") is not None:
                by_priority[Priority(state["priority"]).name.lower()] += 1

        # Time inside the period, by context
        time_by_context: Counter[str] = Counter()
        for session in sessions:
            begin: datetime = max(_aware(session.start_time), start)
            finish: datetime = min(_aware(session.end_time or now), end)
            minutes: int = max(0, int((finish - begin).total_seconds() // 60))
            owner: Task | None = session_tasks.get(session.task_id)
            time_by_context[_context_name(_state_of(owner), contexts)] += minutes

        # Estimated vs. actual, of what was done with measured time — or
        # the time the user said it took, which wins
        accuracy: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
        for entry in completions:
            told: Task | None = tasks.get(entry.task_id)
            actual: int = (
                told.took_minutes
                if told is not None and told.took_minutes
                else spent_on.get(entry.task_id, 0)
            )
            if actual <= 0:
                continue
            state = entry.previous or _state_of(tasks.get(entry.task_id))
            estimate: int = int(state.get("estimate") or 0)
            if estimate <= 0:
                continue
            for key in ("all", _context_name(state, contexts)):
                accuracy[key][0] += 1
                accuracy[key][1] += estimate
                accuracy[key][2] += actual

        hours: Counter[int] = Counter(
            _aware(e.occurred_at).astimezone(zone).hour for e in completions
        )
        done_by_day: Counter[date] = Counter(
            _aware(e.occurred_at).astimezone(zone).date() for e in completions
        )
        created_by_day: Counter[date] = Counter(
            _aware(e.occurred_at).astimezone(zone).date() for e in creations
        )

        return ReportOutputDTO(
            start=first,
            end=last,
            period=label,
            done=len(completions),
            created=sum(created_by_day.values()),
            cancelled=sum(1 for e in ended if e.action == TaskAction.CANCELLED),
            on_time=on_time,
            late=late,
            no_due=no_due,
            days=[
                DayDTO(day=d, done=done_by_day[d], created=created_by_day[d])
                for d in _days(first, last)
            ],
            by_context=_counts(by_context),
            by_priority=[
                CountDTO(label=p.name.lower(), count=by_priority[p.name.lower()])
                for p in sorted(Priority, key=lambda p: -p.value)
                if by_priority[p.name.lower()]
            ],
            series=series,
            hourly=hourly,
            quiet_series=quiet,
            time_spent_minutes=sum(time_by_context.values()),
            time_by_context=_counts(+time_by_context),
            accuracy=[
                AccuracyDTO(
                    label=label, tasks=n, estimated_minutes=est, actual_minutes=act
                )
                for label, (n, est, act) in sorted(
                    accuracy.items(), key=lambda kv: (kv[0] != "all", -kv[1][0])
                )
            ],
            best_hours=(
                [
                    CountDTO(label=f"{hour:02d}:00", count=count)
                    for hour, count in hours.most_common(3)
                ]
                if len(completions) >= 5
                else []
            ),
        )


def _alive(entries: list[TaskHistoryEntry]) -> list[TaskHistoryEntry]:
    """The entries that still stand: neither undone nor an undo."""
    undone: set[Any] = {e.undoes for e in entries if e.undoes is not None}
    return [
        e for e in entries if e.entry_id not in undone and e.action != TaskAction.UNDONE
    ]


def _last_closings(
    entries: list[TaskHistoryEntry],
) -> dict[TaskId, TaskHistoryEntry]:
    """How each task ended, in these entries (oldest first): its last
    completion or cancel, unless a reopen came after it."""
    closing: dict[TaskId, TaskHistoryEntry] = {}
    for entry in entries:
        if entry.action in _CLOSINGS:
            closing[entry.task_id] = entry
        elif entry.action == TaskAction.REOPENED:
            closing.pop(entry.task_id, None)
    return closing


def _counts_for(task: Task | None) -> bool:
    """A task the report counts: there and not deleted."""
    return task is not None and task.deleted_at is None


def _punctuality(
    entry: TaskHistoryEntry, task: Task | None, parents: dict[TaskId, Task]
) -> str:
    """A completion on time or late, against the deadline its task had then
    (none: on time)."""
    deadline: datetime | None = _deadline(entry.previous or _state_of(task), parents)
    if deadline is None or _aware(entry.occurred_at) <= deadline:
        return ON_TIME
    return LATE


def _period(
    request: ReportRequest, today: date, prefs: UserPrefs
) -> tuple[date, date, str]:
    """The first and last day, and how to call the period."""
    if request.period == "week":
        week_start: int = WEEK_STARTS[prefs.week_start]
        return (
            today - timedelta(days=(today.weekday() - week_start) % 7),
            today,
            "this week",
        )
    if request.period == "month":
        return today.replace(day=1), today, "this month"
    if request.period not in (None, ""):
        raise ValidationException(f"Unknown period: {request.period} (week or month).")
    if request.start is None and request.end is None:
        return today - timedelta(days=6), today, "last 7 days"

    last: date = (
        min(_day(request.end, today), today) if request.end is not None else today
    )
    first: date = (
        _day(request.start, today)
        if request.start is not None
        else last - timedelta(days=6)
    )
    if first > today:
        raise ValidationException("A report cannot start in the future.")
    if last < first:
        raise ValidationException("The period ends before it starts.")
    return first, last, "custom"


def _series(
    members: list[Task],
    closings: dict[TaskId, TaskHistoryEntry],
    days: list[date],
    today: date,
    zone: ZoneInfo,
    now: datetime,
) -> tuple[list[SeriesReportDTO], list[HourlySeriesDTO], int]:
    """Each series with a slot in the period (the hourly ones apart), and
    how many others are still going with none in it.

    Args:
        members (list[Task]): Every occurrence of every series (none
            deleted).
        closings (dict[TaskId, TaskHistoryEntry]): How each one ended.
        days (list[date]): The period.
        today (date): Today, where the user is.
        zone (ZoneInfo): Where the user is.
        now (datetime): The current instant.
    """
    by_series: dict[TaskId, list[Task]] = defaultdict(list)
    for task in members:
        if task.series_id is not None:
            by_series[task.series_id].append(task)

    report: list[SeriesReportDTO] = []
    hourly: list[HourlySeriesDTO] = []
    quiet: int = 0
    for series_id, occurrences in by_series.items():
        occurrences.sort(key=lambda t: t.created_at)
        latest: Task = occurrences[-1]
        rule = next((t.recurrence for t in reversed(occurrences) if t.recurrence), None)
        sub_daily: bool = rule is not None and rule.is_sub_daily
        outcomes: dict[TaskId, str | None] = {
            t.id: _outcome(t, closings.get(t.id)) for t in occurrences
        }
        slots: list[Slot] = series_slots(
            occurrences, outcomes, zone, now, hourly=sub_daily
        )
        local_now: datetime = now.astimezone(zone).replace(tzinfo=None)
        in_period: list[Slot] = [
            s
            for s in slots
            if days[0] <= s.day <= days[-1] and (not sub_daily or s.moment <= local_now)
        ]
        if not in_period:
            if latest.recurrence is not None and not latest.status.is_closed:
                quiet += 1
            continue
        if sub_daily:
            per_day: list[HourlyDayDTO] = [
                HourlyDayDTO(
                    day=d,
                    done=sum(1 for s in in_period if s.day == d and s.is_done),
                    slots=sum(1 for s in in_period if s.day == d),
                )
                for d in days
            ]
            done_h: int = sum(d.done for d in per_day)
            hourly.append(
                HourlySeriesDTO(
                    series_id=str(series_id),
                    task_id=str(latest.id),
                    title=str(latest.title),
                    rule=format_task_recurrence(latest.recurrence),
                    done=done_h,
                    slots=len(in_period),
                    rate=done_h / len(in_period),
                    days=per_day,
                )
            )
            continue

        kinds: dict[date, str] = {s.day: s.kind(today) for s in in_period}
        tally: Counter[str] = Counter(kinds.values())
        done: int = tally[ON_TIME] + tally[LATE]
        judged: int = done + tally[SKIPPED] + tally[MISSED]
        report.append(
            SeriesReportDTO(
                series_id=str(series_id),
                task_id=str(latest.id),
                title=str(latest.title),
                rule=format_task_recurrence(latest.recurrence),
                done=done,
                skipped=tally[SKIPPED],
                missed=tally[MISSED],
                pending=tally[PENDING],
                streak=streak_of(slots, today),
                rate=done / judged if judged else None,
                timeline=[kinds.get(d, NO_SLOT) for d in days],
            )
        )
    return (
        sorted(report, key=lambda s: s.title.lower()),
        sorted(hourly, key=lambda s: s.title.lower()),
        quiet,
    )


def _outcome(task: Task, closing: TaskHistoryEntry | None) -> str | None:
    """How an occurrence ended: on time, late, skipped; None while open.
    A snoozed one is judged against its first day's deadline (it fills that
    slot). Closed with no closing in the history (before it existed): by
    its status."""
    if not task.status.is_closed:
        return None
    if closing is None:
        if task.status == TaskStatus.DONE:
            return ON_TIME
        return SKIPPED if task.status == TaskStatus.CANCELLED else None
    if closing.action == TaskAction.CANCELLED:
        return SKIPPED
    if task.snoozed_from is not None:
        # Snoozed, it stays its first day's: late against that day's deadline
        state: dict[str, Any] = closing.previous or _state_of(task)
        first_due: datetime = deadline_of(
            _aware(task.snoozed_from.materialize()),
            int(state.get("estimate") or 0),
            bool(state.get("strict", False)),
        )
        return ON_TIME if _aware(closing.occurred_at) <= first_due else LATE
    return _punctuality(closing, task, {})


def _state_of(task: Task | None) -> dict[str, Any]:
    """A task's current state, when its history kept no snapshot."""
    return task.snapshot() if task is not None else {}


def _due(state: dict[str, Any]) -> datetime | None:
    """The due date in a snapshot, as an instant."""
    if not state.get("due"):
        return None
    return _aware(axiom_date_from_dict(state["due"]).materialize())


def _deadline(state: dict[str, Any], parents: dict[TaskId, Task]) -> datetime | None:
    """When the task in a snapshot became late: due + estimate, or the due
    date when strict (a snapshot without "strict" is a block; one without
    "estimate", from before it was kept, the due date itself). A subtask due
    with its parent: its parent's."""
    due: datetime | None = _due(state)
    if due is None:
        return None
    ref: str | None = state.get("parent_id")
    parent: Task | None = parents.get(TaskId.from_string(ref)) if ref else None
    if parent is not None and parent.due_date is not None:
        if _aware(parent.due_date.materialize()) == due:
            return parent.deadline()
    return deadline_of(
        due, int(state.get("estimate") or 0), bool(state.get("strict", False))
    )


def _context_name(state: dict[str, Any], names: dict[ContextId, str]) -> str:
    raw: str | None = state.get("context_id")
    if not raw:
        return _NO_CONTEXT
    return names.get(ContextId.from_string(raw), _GONE_CONTEXT)


def _counts(counter: Counter[str]) -> list[CountDTO]:
    """Most first; "none" last."""
    return sorted(
        (CountDTO(label=label, count=count) for label, count in counter.items()),
        key=lambda c: (c.label == _NO_CONTEXT, -c.count, c.label.lower()),
    )


def _days(first: date, last: date) -> list[date]:
    return [first + timedelta(days=n) for n in range((last - first).days + 1)]


def _day(value: DateInput, today: date) -> date:
    resolved: date | datetime = resolve_date_input(value, today=today)
    return resolved.date() if isinstance(resolved, datetime) else resolved


def _aware(moment: datetime) -> datetime:
    """Naive instants (what SQLite hands back) are UTC."""
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")
