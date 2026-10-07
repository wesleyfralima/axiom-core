"""When a task becomes late: its due date is when it starts and it lasts its
estimate (a block), or the due date is a hard deadline (strict)."""

from datetime import UTC, datetime, timedelta

import pytest

from b_domain.entities import Task
from b_domain.value_objects import Title, UserId
from b_domain.value_objects.dates import deadline_of

pytestmark = pytest.mark.unit

EIGHT = datetime(2026, 3, 5, 8, 0)


@pytest.mark.parametrize(
    ("due", "estimate", "strict", "expected"),
    [
        # A block: due + estimate
        (EIGHT, 120, False, datetime(2026, 3, 5, 10, 0)),
        # Strict: the due date itself
        (EIGHT, 120, True, EIGHT),
        # No estimate: the due date
        (EIGHT, 0, False, EIGHT),
        # Never into the next day: a date with no time typed is 23:59
        (datetime(2026, 3, 5, 23, 59), 30, False, datetime(2026, 3, 5, 23, 59, 59)),
        (datetime(2026, 3, 5, 23, 0), 120, False, datetime(2026, 3, 5, 23, 59, 59)),
        # Aware stays aware
        (
            EIGHT.replace(tzinfo=UTC),
            30,
            False,
            datetime(2026, 3, 5, 8, 30, tzinfo=UTC),
        ),
    ],
)
def test_deadline_of(
    due: datetime, estimate: int, strict: bool, expected: datetime
) -> None:
    assert deadline_of(due, estimate, strict) == expected


def _task(
    due: datetime = EIGHT,
    estimate: int = 120,
    strict: bool = False,
    parent: Task | None = None,
) -> Task:
    return Task.create(
        now=EIGHT.replace(tzinfo=UTC) - timedelta(days=1),
        user_id=UserId(),
        title=Title("Write the report"),
        due_date=due,
        tz_name="UTC",
        estimated_duration_minutes=estimate,
        strict_due=strict,
        parent_id=parent.id if parent else None,
    )


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 3, 5, hour, minute, tzinfo=UTC)


def test_a_block_is_late_only_after_its_estimate() -> None:
    task = _task()
    assert not task.is_overdue(_at(9, 45))
    assert not task.is_overdue(_at(10, 0))
    assert task.is_overdue(_at(10, 1))


def test_a_strict_due_date_is_late_right_after_it() -> None:
    task = _task(strict=True)
    assert not task.is_overdue(_at(8, 0))
    assert task.is_overdue(_at(8, 1))
    assert task.deadline() == _at(8, 0)


def test_no_due_date_is_never_late() -> None:
    task = Task.create(now=_at(8), user_id=UserId(), title=Title("Someday"))
    assert task.deadline() is None
    assert not task.is_overdue(_at(23))


def test_a_subtask_due_with_its_parent_shares_its_deadline() -> None:
    parent = _task(estimate=120)
    with_it = _task(estimate=15, parent=parent)
    earlier = _task(due=datetime(2026, 3, 5, 7, 0), estimate=15, parent=parent)

    assert with_it.deadline(parent) == _at(10, 0)
    assert not with_it.is_overdue(_at(9, 45), parent)
    # Without its parent at hand: its own
    assert with_it.deadline() == _at(8, 15)
    # An earlier due date of its own: its own block
    assert earlier.deadline(parent) == _at(7, 15)


def test_strict_is_kept_by_the_snapshot_and_undo() -> None:
    task = _task()
    before = task.snapshot()
    task.set_strict_due(_at(9), True)
    assert task.snapshot()["strict"] is True

    task.revert_to(_at(9, 5), before, undoes=task.id, action="edited")

    assert task.strict_due is False
