from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from a_core.exceptions import InvalidStateTransition, ValidationException
from b_domain.entities import Task
from b_domain.value_objects import (
    ContextId,
    Priority,
    RecurrenceInterval,
    Title,
    UserId,
)
from b_domain.value_objects.dates import AxiomDate, DueDate
from b_domain.value_objects.enums import EnergyLevel, TaskComplexity
from b_domain.value_objects.recurrences import SimpleIntervalRule

# ============================================================
# Helpers
# ============================================================


def create_task_with_recurrence(
    due_date: datetime,
    interval: int = 1,
    freq: RecurrenceInterval = RecurrenceInterval.DAILY,
    is_floating: bool = True,
    tz_name: str = "UTC",
    end_date: datetime | None = None,
) -> Task:
    """Helper to quickly build a task with a recurrence."""

    # ------------------------------------------------------------------
    # 1. Construir AxiomDate corretamente
    # ------------------------------------------------------------------

    if is_floating:
        start_axiom = AxiomDate.floating(
            due_date.replace(tzinfo=None),
            tz_name,
        )
    else:
        if due_date.tzinfo is None:
            due_date = due_date.replace(tzinfo=UTC)
        start_axiom = AxiomDate.fixed(due_date)

    # ------------------------------------------------------------------
    # 2. Converter end_date (se existir)
    # ------------------------------------------------------------------

    end_axiom = None
    if end_date:
        if is_floating:
            end_axiom = AxiomDate.floating(
                end_date.replace(tzinfo=None),
                tz_name,
            )
        else:
            if end_date.tzinfo is None:
                end_date = end_date.replace(tzinfo=UTC)
            end_axiom = AxiomDate.fixed(end_date)

    # ------------------------------------------------------------------
    # 3. Build the recurrence rule
    # ------------------------------------------------------------------

    recurrence = SimpleIntervalRule(
        frequency=freq, interval=interval, start_date=start_axiom, end_date=end_axiom
    )

    # ------------------------------------------------------------------
    # 4. DueDate (compatible with the current domain)
    # ------------------------------------------------------------------

    if is_floating:
        due = DueDate.floating(
            due_date.replace(tzinfo=None),
            tz_name,
        )
    else:
        due = DueDate.fixed(due_date)

    # ------------------------------------------------------------------
    # 5. Create the task
    # ------------------------------------------------------------------

    return Task.create(
        now=datetime.now(),
        user_id=UserId(uuid4()),
        title=Title("Test Task"),
        due_date=due.value,
        is_floating=is_floating,
        tz_name=tz_name,
        recurrence=recurrence,
    )


# ============================================================
# Tests: create_next_occurrence
# ============================================================


def test_next_occurrence_simple_daily() -> None:
    """
    Scenario: the task is due today (Jan 1). I complete it today.
    Expected: next task for tomorrow (Jan 2).
    """

    # Jan 1 at 09:00
    due_dt = datetime(2026, 1, 1, 9, 0)
    now = datetime(2026, 1, 1, 10, 0)  # 1 hour after the due time

    task = create_task_with_recurrence(due_dt)

    next_task = task.create_next_occurrence(now=now)

    assert next_task is not None
    assert next_task.due_date is not None
    assert next_task.due_date.value == datetime(2026, 1, 2, 9, 0)
    assert next_task.due_date.is_floating is True


def test_next_occurrence_catch_up_logic() -> None:
    """
    Scenario: the task was due 5 days ago (Jan 5). Today is Jan 10.
    Expected: skip the 6th, 7th, 8th, 9th and 10th and schedule for Jan 11.
    (Jan 10 09:00 has already passed relative to 'now', Jan 10 10:00.)
    """
    due_dt = datetime(2026, 1, 5, 9, 0)
    now = datetime(2026, 1, 10, 10, 0)

    task = create_task_with_recurrence(due_dt)

    # catch_up=True is the default
    next_task = task.create_next_occurrence(now=now, catch_up=True)

    assert next_task is not None
    assert next_task.due_date is not None
    assert next_task.due_date.value == datetime(2026, 1, 11, 9, 0)


def test_next_occurrence_strict_mode_financial() -> None:
    """
    Scenario: the task was due 5 days ago (Jan 5). Today is Jan 10.
    Expectativa: catch_up=False (Modo Financeiro).
    The system must create the EXACT next sequential occurrence (Jan 6), even if late.
    """
    due_dt = datetime(2026, 1, 5, 9, 0)
    now = datetime(2026, 1, 10, 10, 0)

    task = create_task_with_recurrence(due_dt)

    # Desativa o catch-up
    next_task = task.create_next_occurrence(now=now, catch_up=False)

    assert next_task is not None
    assert next_task.due_date is not None
    assert next_task.due_date.value == datetime(2026, 1, 6, 9, 0)  # Atrasada


def test_recurrence_ends_by_date() -> None:
    """
    Scenario: the recurrence has an end date (until).
    Expected: return None once past that date.
    """
    due_dt = datetime(2026, 1, 1, 9, 0)
    end_date = datetime(2026, 1, 1, 23, 59)  # ends today
    now = datetime(2026, 1, 1, 10, 0)

    task = create_task_with_recurrence(due_dt, end_date=end_date)

    # The next one would be Jan 2, but Jan 2 > end date
    next_task = task.create_next_occurrence(now=now)

    assert next_task is None


def test_timezone_consistency_fixed_task() -> None:
    """
    Scenario: fixed task (UTC).
    Expected: the next task is also born fixed (UTC).
    """

    due_dt = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
    now = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)

    task = create_task_with_recurrence(due_dt, is_floating=False)

    next_task = task.create_next_occurrence(now=now)

    assert next_task is not None
    assert next_task.due_date is not None
    assert next_task.due_date.is_floating is False
    assert next_task.due_date.value.tzinfo is not None  # must be aware
    assert next_task.due_date.value == datetime(2026, 1, 2, 9, 0, tzinfo=UTC)


def test_timezone_comparison_mixed_inputs() -> None:
    """
    Scenario: floating task (naive) vs aware 'now' (UTC).
    Expected: the system normalizes internally and does not break with TypeError.
    """

    # Floating task at 09:00
    due_dt = datetime(2026, 1, 5, 9, 0)

    # 'Now' is 13:00 UTC (which would be '10:00' in SP, '-3').
    # A floating task is due at 09:00 local time.
    # 10:00 (now) > 09:00 (due). So today's has already passed.
    # The next one must be the 11th.
    now_aware = datetime(2026, 1, 10, 13, 0, tzinfo=UTC)

    task = create_task_with_recurrence(due_dt, is_floating=True)

    next_task = task.create_next_occurrence(now=now_aware, catch_up=True)

    assert next_task is not None
    assert next_task.due_date is not None
    assert next_task.due_date.is_floating is True
    assert next_task.due_date.value == datetime(2026, 1, 11, 9, 0)  # Naive


def test_next_occurrence_keeps_what_the_user_set() -> None:
    """The next occurrence inherits context, energy, complexity and estimate."""

    task = create_task_with_recurrence(datetime(2026, 1, 1, 9, 0))
    task.context_id = ContextId(uuid4())
    task.required_energy_level = EnergyLevel.PEAK
    task.complexity = TaskComplexity.HIGH
    task.priority = Priority.CRITICAL
    task.estimated_duration_minutes = 90

    next_task = task.create_next_occurrence(now=datetime(2026, 1, 1, 10, 0))

    assert next_task is not None
    assert next_task.id != task.id
    assert next_task.context_id == task.context_id
    assert next_task.required_energy_level is EnergyLevel.PEAK
    assert next_task.complexity is TaskComplexity.HIGH
    assert next_task.priority is Priority.CRITICAL
    assert next_task.estimated_duration_minutes == 90


def test_count_is_carried_as_what_is_left() -> None:
    task = create_task_with_recurrence(datetime(2026, 3, 9, 7, 0))
    assert task.recurrence is not None
    task.recurrence = replace(task.recurrence, count=3)

    second = task.create_next_occurrence(datetime(2026, 3, 9, 8, 0))
    assert second is not None and second.recurrence is not None
    assert second.recurrence.count == 2

    third = second.create_next_occurrence(datetime(2026, 3, 10, 8, 0))
    assert third is not None and third.recurrence is not None
    assert third.recurrence.count == 1

    assert third.create_next_occurrence(datetime(2026, 3, 11, 8, 0)) is None


def test_a_rule_of_another_kind_is_refused() -> None:
    floating = create_task_with_recurrence(datetime(2026, 3, 9, 7, 0))
    fixed_rule = create_task_with_recurrence(
        datetime(2026, 3, 9, 7, 0), is_floating=False
    ).recurrence

    with pytest.raises(ValidationException, match="fixed or both floating"):
        floating.change_recurrence(datetime(2026, 3, 9), fixed_rule)


# ============================================================
# The next occurrence's ID
# ============================================================


def test_the_next_occurrence_has_the_same_id_on_every_device() -> None:
    task = create_task_with_recurrence(datetime(2026, 1, 1, 9, 0))
    now = datetime(2026, 1, 1, 10, 0)

    # Two devices complete the same occurrence, at different moments
    here = task.create_next_occurrence(now)
    there = task.create_next_occurrence(now.replace(minute=30))

    assert here is not None and there is not None
    assert here.id == there.id
    assert here.series_id == task.series_id
    # …and the one after it follows the series, not the first ID
    after = here.create_next_occurrence(now)
    assert after is not None
    assert after.id != here.id
    assert after.series_id == task.series_id


def test_another_series_or_date_is_another_occurrence() -> None:
    first = create_task_with_recurrence(datetime(2026, 1, 1, 9, 0))
    other = create_task_with_recurrence(datetime(2026, 1, 1, 9, 0))
    now = datetime(2026, 1, 1, 10, 0)

    one = first.create_next_occurrence(now)
    two = other.create_next_occurrence(now)
    later = first.create_next_occurrence(datetime(2026, 1, 5, 10, 0))

    assert one is not None and two is not None and later is not None
    assert one.id != two.id
    assert one.id != later.id  # catch-up: a later date


def test_a_fixed_occurrence_id_does_not_depend_on_the_offset() -> None:
    task = create_task_with_recurrence(
        datetime(2026, 1, 1, 12, 0, tzinfo=UTC), is_floating=False
    )
    ahead = replace(
        task,
        due_date=DueDate.fixed(
            datetime(2026, 1, 1, 9, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
        ),
    )
    now = datetime(2026, 1, 1, 13, 0, tzinfo=UTC)

    one = task.create_next_occurrence(now)
    two = ahead.create_next_occurrence(now)

    assert one is not None and two is not None
    assert one.id == two.id


def test_a_task_from_before_series_starts_its_own() -> None:
    task = create_task_with_recurrence(datetime(2026, 1, 1, 9, 0))
    task.series_id = None

    following = task.create_next_occurrence(datetime(2026, 1, 1, 10, 0))

    assert following is not None
    assert following.series_id == task.id


def test_only_a_deleted_occurrence_comes_back() -> None:
    task = create_task_with_recurrence(datetime(2026, 1, 1, 9, 0))
    now = datetime(2026, 1, 1, 10, 0)
    kept = task.create_next_occurrence(now)
    fresh = task.create_next_occurrence(now)
    assert kept is not None and fresh is not None

    with pytest.raises(InvalidStateTransition):
        kept.come_back_as(fresh)

    kept.mark_deleted(now)
    with pytest.raises(ValidationException):
        kept.come_back_as(task)

    kept.pull_events()
    kept.come_back_as(fresh)
    assert kept.deleted_at is None
    assert [type(e).__name__ for e in kept.pull_events()] == ["TaskCreatedEvent"]
    assert fresh.peek_events() == []
