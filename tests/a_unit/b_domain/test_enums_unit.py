import pytest

from a_core.exceptions import InvalidValueError
from b_domain.value_objects import (
    Priority,
    RecurrenceInterval,
    TaskStatus,
)
from b_domain.value_objects.enums import EnergyLevel, TaskComplexity

# ============================================================
# Group 1: TaskStatus Transitions
# ============================================================


@pytest.mark.parametrize(
    "current,allowed",
    [
        (
            TaskStatus.PENDING,
            {
                TaskStatus.PENDING,
                TaskStatus.SUGGESTED,
                TaskStatus.IN_PROGRESS,
                TaskStatus.DONE,
                TaskStatus.CANCELLED,
                TaskStatus.ARCHIVED,
                TaskStatus.BLOCKED,
                TaskStatus.SOMEDAY,
                TaskStatus.SKIPPED,
                TaskStatus.ABANDONED,
            },
        ),
        (
            TaskStatus.IN_PROGRESS,
            {
                TaskStatus.IN_PROGRESS,
                TaskStatus.DONE,
                TaskStatus.PAUSED,
                TaskStatus.DEFERRED,
                TaskStatus.ABANDONED,
                TaskStatus.CANCELLED,
                TaskStatus.PENDING,
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
    ],
)
def test_task_status_allows_expected_transitions(
    current: TaskStatus, allowed: set[TaskStatus]
) -> None:
    """Ensure TaskStatus allows only expected transitions."""

    for status in TaskStatus:
        assert current.can_transition_to(status) is (status in allowed)


def test_task_status_archived_is_terminal() -> None:
    """Ensure ARCHIVED is a terminal TaskStatus with no outgoing transitions."""

    for status in TaskStatus:
        assert (
            TaskStatus.ARCHIVED.can_transition_to(status) is False
            if status != TaskStatus.ARCHIVED
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
# Group 3: Parsing levels typed by the user
# ============================================================


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("high", Priority.HIGH),
        ("HIGH", Priority.HIGH),
        (" Critical ", Priority.CRITICAL),
        ("1", Priority.LOW),
        (2, Priority.MEDIUM),
        (Priority.HIGH, Priority.HIGH),
    ],
)
def test_priority_parse_accepts_name_or_number(
    raw: str | int, expected: Priority
) -> None:
    assert Priority.parse(raw) is expected


@pytest.mark.parametrize("raw", ["urgent", "", "0", "5", "-1", "hi"])
def test_priority_parse_rejects_unknown(raw: str) -> None:
    with pytest.raises(InvalidValueError, match="Invalid priority"):
        Priority.parse(raw)


def test_complexity_parse_accepts_separators() -> None:
    assert TaskComplexity.parse("very-low") is TaskComplexity.VERY_LOW
    assert TaskComplexity.parse("very high") is TaskComplexity.VERY_HIGH
    assert TaskComplexity.parse("very_high") is TaskComplexity.VERY_HIGH


def test_parse_error_lists_the_options() -> None:
    with pytest.raises(InvalidValueError) as exc:
        EnergyLevel.parse("tired")

    assert str(exc.value) == (
        "Invalid energy level: 'tired'. "
        "Valid options are: drained, low, balanced, high, peak."
    )


def test_level_str_is_readable() -> None:
    assert str(Priority.HIGH) == "High"
    assert str(TaskComplexity.VERY_LOW) == "Very low"


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


@pytest.mark.parametrize("status", list(TaskStatus))
def test_closed_statuses(status: TaskStatus) -> None:
    expected = status in {TaskStatus.DONE, TaskStatus.CANCELLED, TaskStatus.ARCHIVED}

    assert status.is_closed is expected
