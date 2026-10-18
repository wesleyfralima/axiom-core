"""A recurring series judged by its slots (product Backlog 08).

A **slot** is a moment the rule says should have had an occurrence. The
slots come from the occurrences themselves: each one fills its own (its
original day when snoozed — ``snoozed_from`` — else the due date it had
when it closed: an edit moves it), and the slots between one occurrence and
the next follow the earlier one's rule — so a rule changed over time gives
each stretch its own slots. The series starts at its first occurrence; it
goes on past the latest one only while that one is open (a closed latest
with nothing after it is a series that ended: ``cancel --series``, its
``count``, its ``--until``).

A slot has one outcome — the best of the occurrences in it (the sync's
copies, a snooze keeping both): done on time, done late, skipped, or none
recorded (missed when its day is gone, pending today). A daily or coarser
series has one slot per day; an hourly one, one per moment.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from b_domain.entities import Task
from b_domain.value_objects import TaskId

ON_TIME: str = "on_time"
LATE: str = "late"
SKIPPED: str = "skipped"
MISSED: str = "missed"
PENDING: str = "pending"
NO_SLOT: str = "none"

# Best first: a slot keeps the best outcome of its occurrences
_BEST: tuple[str, ...] = (ON_TIME, LATE, SKIPPED)
_DONE: frozenset[str] = frozenset({ON_TIME, LATE})

# A series walked one slot at a time never goes further than this
_MOST_SLOTS: int = 50_000


@dataclass(frozen=True, kw_only=True)
class Slot:
    """One moment the series should have had an occurrence.

    Attributes:
        moment (datetime): When, as wall-clock time where the user is.
        outcome (str | None): ``on_time``, ``late`` or ``skipped``; None
            when nothing was recorded.
    """

    moment: datetime
    outcome: str | None

    @property
    def day(self) -> date:
        return self.moment.date()

    @property
    def is_done(self) -> bool:
        return self.outcome in _DONE

    def kind(self, today: date) -> str:
        """What the slot shows: its outcome, or missed (its day is gone) or
        pending (today)."""
        if self.outcome is not None:
            return self.outcome
        return PENDING if self.day >= today else MISSED


def series_slots(
    occurrences: Iterable[Task],
    outcomes: dict[TaskId, str | None],
    zone: ZoneInfo,
    now: datetime,
    *,
    hourly: bool = False,
) -> list[Slot]:
    """The slots of one series, in order, up to ``now``.

    Args:
        occurrences (Iterable[Task]): The series' occurrences (none deleted).
        outcomes (dict[TaskId, str | None]): How each one ended
            (``on_time``, ``late``, ``skipped``; None or absent: it did not).
        zone (ZoneInfo): Where the user is.
        now (datetime): The current instant (aware).
        hourly (bool): One slot per moment (an hourly series), not per day.

    Returns:
        list[Slot]: Every slot from the first occurrence's on — the latest
        open one's rule walked up to now; a slot ahead only when an
        occurrence fills it.
    """
    until: datetime = _local(now, zone)

    def key(moment: datetime) -> datetime | date:
        return moment.replace(second=0, microsecond=0) if hourly else moment.date()

    anchors: list[tuple[datetime, Task]] = sorted(
        (
            (_local(_slot_value(t), zone), t)
            for t in occurrences
            if t.snoozed_from is not None or t.due_date is not None
        ),
        key=lambda pair: pair[0],
    )
    found: dict[datetime | date, tuple[datetime, str | None]] = {}

    def fill(moment: datetime, outcome: str | None) -> None:
        at: datetime | date = key(moment)
        first, best = found.get(at, (moment, None))
        found[at] = (first, _better(best, outcome))

    rule = None
    for index, (moment, task) in enumerate(anchors):
        fill(moment, outcomes.get(task.id))
        rule = task.recurrence or rule
        if rule is None:
            continue
        following: datetime | None = (
            anchors[index + 1][0] if index + 1 < len(anchors) else None
        )
        if following is None and task.status.is_closed:
            break  # the series ended with it
        left: int | None = (
            rule.count - 1 if following is None and rule.count is not None else None
        )
        last: datetime = _slot_value(task)
        for _ in range(_MOST_SLOTS):
            if left is not None and left <= 0:
                break
            upcoming: datetime | None = rule.get_next_occurrence(last)
            if upcoming is None:
                break
            at: datetime = _local(upcoming, zone)
            if at <= _local(last, zone):
                break
            if following is not None and key(at) >= key(following):
                break
            if following is None and at > until:
                break
            fill(at, None)
            last = upcoming
            if left is not None:
                left -= 1

    return [Slot(moment=m, outcome=o) for m, o in sorted(found.values())]


def streak_of(slots: list[Slot], today: date) -> int:
    """Done slots in a row up to the latest one gone by (today's, still
    pending, does not break it; a slot ahead does not count)."""
    count: int = 0
    for slot in reversed(slots):
        if slot.day > today or (slot.day == today and slot.outcome is None):
            continue
        if not slot.is_done:
            break
        count += 1
    return count


def _better(one: str | None, other: str | None) -> str | None:
    """The better of two outcomes (None: nothing recorded, the worst)."""
    ranked: list[str] = [o for o in (one, other) if o is not None]
    return min(ranked, key=_BEST.index) if ranked else None


def _slot_value(task: Task) -> datetime:
    """The moment an occurrence stands for, in its rule's own kind: where it
    was first due when snoozed, else its due date."""
    due = task.snoozed_from or task.due_date
    assert due is not None
    return due.value


def _local(moment: datetime, zone: ZoneInfo) -> datetime:
    """Wall-clock time where the user is: a naive value already is one (a
    floating date); an aware one is an instant."""
    if moment.tzinfo is None:
        return moment
    return moment.astimezone(zone).replace(tzinfo=None)
