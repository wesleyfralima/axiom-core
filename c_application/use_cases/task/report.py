"""`axpro report`: what was done in a period, from the history and the tasks.

Nothing new is collected: completions, cancellations and creations come
from the history (an undone one does not count), and a completion is on
time or late against the due date the task had *when it was completed*
(the snapshot in its history entry), so moving a date later does not
rewrite the past.
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
from b_domain.value_objects.recurrences._serial import axiom_date_from_dict
from b_domain.value_objects.task_history import TaskAction, TaskHistoryEntry
from c_application.use_cases.task.timer import time_of
from c_application.utils import format_task_recurrence
from c_application.utils.date_input import DateInput, local_today, resolve_date_input
from c_application.utils.recurrence_input import WEEK_STARTS

_NO_CONTEXT: str = "none"
_GONE_CONTEXT: str = "(deleted context)"

# What happened to a series on one day (worst wins when several did)
_NOTHING: str = "none"
_ON_TIME: str = "on_time"
_LATE: str = "late"
_SKIPPED: str = "skipped"
_WORSE: tuple[str, ...] = (_NOTHING, _ON_TIME, _LATE, _SKIPPED)


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
    """One recurring series.

    Attributes:
        series_id (str): The series.
        task_id (str): Its latest occurrence (what to open).
        title (str): Its latest occurrence's title.
        rule (str | None): How it repeats now (None: it stopped).
        done (int): Occurrences completed in the period.
        missed (int): Occurrences cancelled (skipped) in the period.
        streak (int): The current streak: completed in a row, up to the
            latest closed one (not limited to the period).
        rate (float | None): Completed ÷ (completed + skipped) in the period
            (None when neither happened).
        timeline (list[str]): One entry per day of the period: "none" (nothing
            happened), "on_time", "late" or "skipped" (the worst of the day).
    """

    series_id: str
    task_id: str
    title: str
    rule: str | None
    done: int
    missed: int
    streak: int
    rate: float | None
    timeline: list[str] = field(default_factory=list)


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
    # Series still going that had nothing in the period (not listed)
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
            prefs: UserPrefs = user.preferences if user else UserPrefs()
            zone: ZoneInfo = _zone(prefs.timezone)
            today: date = local_today(now, prefs.timezone)
            first, last, label = _period(request, today, prefs)

            start: datetime = datetime.combine(first, time(), tzinfo=zone)
            end: datetime = datetime.combine(
                last + timedelta(days=1), time(), tzinfo=zone
            )
            # Up to now as well: an undo after the period still cancels a change
            fetched: list[TaskHistoryEntry] = await uow.task_history.between(
                user_id, start, max(end, now + timedelta(days=1))
            )
            undone: set[Any] = {e.undoes for e in fetched if e.undoes is not None}
            entries: list[TaskHistoryEntry] = [
                e
                for e in fetched
                if _aware(e.occurred_at) < end
                and e.entry_id not in undone
                and e.action != TaskAction.UNDONE
            ]

            completions = [e for e in entries if e.action == TaskAction.COMPLETED]
            tasks: dict[TaskId, Task] = (
                {
                    t.id: t
                    for t in await uow.tasks.list(
                        TaskFilter(
                            user_id=user_id,
                            ids=list({e.task_id for e in completions}),
                            deleted=None,
                            limit=10_000,
                        )
                    )
                }
                if completions
                else {}
            )
            contexts: dict[ContextId, str] = {
                c.id: c.name for c in await uow.contexts.list_by_user(user_id)
            }
            in_series: list[Task] = await uow.tasks.list(
                TaskFilter(user_id=user_id, in_series=True, limit=10_000)
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
                if _aware(e.end_time or now) > start
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
        punctuality: dict[Any, str] = {}
        by_context: Counter[str] = Counter()
        by_priority: Counter[str] = Counter()
        for entry in completions:
            state: dict[str, Any] = entry.previous or _state_of(
                tasks.get(entry.task_id)
            )
            due: datetime | None = _due(state)
            if due is None:
                no_due += 1
                punctuality[entry.entry_id] = _ON_TIME
            elif _aware(entry.occurred_at) <= due:
                on_time += 1
                punctuality[entry.entry_id] = _ON_TIME
            else:
                late += 1
                punctuality[entry.entry_id] = _LATE
            by_context[_context_name(state, contexts)] += 1
            if state.get("priority") is not None:
                by_priority[Priority(state["priority"]).name.lower()] += 1

        series, quiet = _series(
            in_series, entries, _days(first, last), zone, punctuality
        )

        # Time inside the period, by context
        time_by_context: Counter[str] = Counter()
        for session in sessions:
            begin: datetime = max(_aware(session.start_time), start)
            finish: datetime = min(_aware(session.end_time or now), end)
            minutes: int = max(0, int((finish - begin).total_seconds() // 60))
            owner: Task | None = session_tasks.get(session.task_id)
            time_by_context[_context_name(_state_of(owner), contexts)] += minutes

        # Estimated vs. actual, of what was done with measured time
        accuracy: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
        for entry in completions:
            actual: int = spent_on.get(entry.task_id, 0)
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
            _aware(e.occurred_at).astimezone(zone).date()
            for e in entries
            if e.action == TaskAction.CREATED
        )

        return ReportOutputDTO(
            start=first,
            end=last,
            period=label,
            done=len(completions),
            created=sum(created_by_day.values()),
            cancelled=sum(1 for e in entries if e.action == TaskAction.CANCELLED),
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
    entries: list[TaskHistoryEntry],
    days: list[date],
    zone: ZoneInfo,
    punctuality: dict[Any, str],
) -> tuple[list[SeriesReportDTO], int]:
    """Each series with something done or skipped in the period, and how
    many others are still going with nothing in it."""
    by_series: dict[TaskId, list[Task]] = defaultdict(list)
    for task in members:
        if task.series_id is not None:
            by_series[task.series_id].append(task)
    ids_in_period: Counter[tuple[TaskId, TaskAction]] = Counter(
        (e.task_id, e.action) for e in entries
    )

    report: list[SeriesReportDTO] = []
    quiet: int = 0
    for series_id, occurrences in by_series.items():
        occurrences.sort(key=lambda t: t.created_at)
        latest: Task = occurrences[-1]
        done = sum(ids_in_period[(t.id, TaskAction.COMPLETED)] for t in occurrences)
        missed = sum(ids_in_period[(t.id, TaskAction.CANCELLED)] for t in occurrences)
        if not (done or missed):
            if latest.recurrence is not None and not latest.status.is_closed:
                quiet += 1
            continue

        closed: list[Task] = [
            t
            for t in occurrences
            if t.status in (TaskStatus.DONE, TaskStatus.CANCELLED)
        ]
        streak: int = 0
        for task in reversed(closed):
            if task.status != TaskStatus.DONE:
                break
            streak += 1

        ids: set[TaskId] = {t.id for t in occurrences}
        worst: dict[date, str] = {}
        for entry in entries:
            if entry.task_id not in ids:
                continue
            if entry.action == TaskAction.COMPLETED:
                kind: str = punctuality.get(entry.entry_id, _ON_TIME)
            elif entry.action == TaskAction.CANCELLED:
                kind = _SKIPPED
            else:
                continue
            day: date = _aware(entry.occurred_at).astimezone(zone).date()
            if _WORSE.index(kind) > _WORSE.index(worst.get(day, _NOTHING)):
                worst[day] = kind

        report.append(
            SeriesReportDTO(
                series_id=str(series_id),
                task_id=str(latest.id),
                title=str(latest.title),
                rule=format_task_recurrence(latest.recurrence),
                done=done,
                missed=missed,
                streak=streak,
                rate=done / (done + missed),
                timeline=[worst.get(d, _NOTHING) for d in days],
            )
        )
    return sorted(report, key=lambda s: s.title.lower()), quiet


def _state_of(task: Task | None) -> dict[str, Any]:
    """A task's current state, when its history kept no snapshot."""
    return task.snapshot() if task is not None else {}


def _due(state: dict[str, Any]) -> datetime | None:
    """The due date in a snapshot, as an instant."""
    if not state.get("due"):
        return None
    return _aware(axiom_date_from_dict(state["due"]).materialize())


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
