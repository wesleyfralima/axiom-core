import pytest

from b_domain.value_objects import (
    TaskStatus,
    Priority,
    RecurrenceInterval,
)


# ============================================================
# Group 1: TaskStatus Transitions
# ============================================================

@pytest.mark.parametrize("current,allowed", [
    (
        TaskStatus.PENDING,
        {
            TaskStatus.PENDING,
            TaskStatus.SUGGESTED, TaskStatus.IN_PROGRESS, TaskStatus.DONE,
            TaskStatus.CANCELLED, TaskStatus.ARCHIVED, TaskStatus.BLOCKED,
            TaskStatus.SOMEDAY, TaskStatus.SKIPPED, TaskStatus.ABANDONED,
        },
    ),
    (
        TaskStatus.IN_PROGRESS,
        {
            TaskStatus.IN_PROGRESS,
            TaskStatus.DONE, TaskStatus.PAUSED, TaskStatus.DEFERRED,
            TaskStatus.ABANDONED, TaskStatus.CANCELLED, TaskStatus.PENDING,
        },
    ),
    (
        TaskStatus.REOPENED,
        {
            TaskStatus.REOPENED,
            TaskStatus.PENDING,
            TaskStatus.SUGGESTED,
            TaskStatus.IN_PROGRESS,
            TaskStatus.DONE,
        },
    ),
])
def test_task_status_allows_expected_transitions(current: TaskStatus, allowed: set[TaskStatus]) -> None:
    """Ensure TaskStatus allows only expected transitions."""

    for status in TaskStatus:
        assert current.can_transition_to(status) is (status in allowed)


def test_task_status_archived_is_terminal() -> None:
    """Ensure ARCHIVED is a terminal TaskStatus with no outgoing transitions."""

    for status in TaskStatus:
        assert (
            TaskStatus.ARCHIVED.can_transition_to(status)
            is False if status != TaskStatus.ARCHIVED
            else True
        )


# ============================================================
# Group 2: Priority Weights
# ============================================================

def test_priority_weights_are_correct() -> None:
    """Ensure Priority weights are correctly defined for sorting."""

    assert Priority.CRITICAL == 4
    assert Priority.HIGH == 3
    assert Priority.MEDIUM == 2
    assert Priority.LOW == 1


def test_priority_weight_allows_sorting() -> None:
    """Ensure Priority weights allow correct sorting order."""

    priorities: list[Priority] = [
        Priority.LOW,
        Priority.CRITICAL,
        Priority.MEDIUM,
        Priority.HIGH,
    ]

    sorted_priorities: list[Priority] = sorted(priorities)

    assert sorted_priorities == [
        Priority.LOW,
        Priority.MEDIUM,
        Priority.HIGH,
        Priority.CRITICAL,
    ]


# ============================================================
# Group 4: RecurrenceInterval Values
# ============================================================

def test_recurrence_interval_values() -> None:
    """Ensure RecurrenceInterval enum values are correctly defined."""

    assert RecurrenceInterval.HOURLY.value == "HO"
    assert RecurrenceInterval.DAILY.value == "DA"
    assert RecurrenceInterval.WEEKLY.value == "WE"
    assert RecurrenceInterval.MONTHLY.value == "MO"
    assert RecurrenceInterval.YEARLY.value == "YE"
