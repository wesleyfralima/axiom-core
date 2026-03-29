from enum import IntEnum, StrEnum
from functools import cache


class TaskStatus(StrEnum):
    """Enumeration of possible Task statuses.

    Represents the lifecycle of a task across planning, execution,
    and completion, including feedback states.
    """

    # --- Planning and Intention (Axiom Pro) ---
    SOMEDAY = "someday"         # In backlog, but outside Flow Engine scope (incubation)
    PENDING = "pending"         # Active for Flow Engine, waiting for execution
    BLOCKED = "blocked"         # Waiting for external dependency

    # --- Flow (Axiom Flow) ---
    SUGGESTED = "suggested"     # Suggested by Flow Engine

    # --- Execution ---
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"           # Temporary interruption (momentum preserved)

    # --- Completion ---
    DONE = "done"

    # --- Flow Feedback (could be invisible in Pro) ---
    SKIPPED = "skipped"         # User declined Flow suggestion
    DEFERRED = "deferred"       # User started but returned task to list
    ABANDONED = "abandoned"     # User abandoned or system inferred stop

    CANCELLED = "cancelled"
    REOPENED = "reopened"       # Reactivated after completion or cancellation
    ARCHIVED = "archived"       # Terminal state, no return

    @classmethod
    @cache
    def _get_transitions(cls) -> dict["TaskStatus", set["TaskStatus"]]:
        """Return cached state machine transitions.

        This defines valid transitions between statuses. Using a cached
        class method avoids recreating the dictionary on every check.
        """

        return {
            cls.SOMEDAY: {
                cls.PENDING, cls.CANCELLED, cls.ARCHIVED,
            },

            cls.PENDING: {
                cls.SUGGESTED, cls.IN_PROGRESS, cls.DONE,
                cls.CANCELLED, cls.ARCHIVED, cls.BLOCKED,
                cls.SOMEDAY, cls.SKIPPED, cls.ABANDONED,
            },

            cls.BLOCKED: {
                cls.PENDING, cls.CANCELLED,
            },

            cls.SUGGESTED: {
                cls.IN_PROGRESS, cls.DONE, cls.SKIPPED,
                cls.PENDING, cls.CANCELLED,
            },

            cls.IN_PROGRESS: {
                cls.DONE, cls.PAUSED, cls.DEFERRED,
                cls.ABANDONED, cls.CANCELLED, cls.PENDING,
            },

            cls.PAUSED: {
                cls.IN_PROGRESS, cls.DONE, cls.DEFERRED,
                cls.ABANDONED,
            },

            cls.SKIPPED: {
                cls.PENDING, cls.DONE, cls.ARCHIVED,
            },

            cls.DEFERRED: {
                cls.PENDING,
            },

            cls.ABANDONED: {
                cls.PENDING, cls.ARCHIVED, cls.CANCELLED,
            },

            cls.DONE: {
                cls.REOPENED, cls.ARCHIVED,
            },

            cls.CANCELLED: {
                cls.REOPENED, cls.ARCHIVED,
            },

            cls.REOPENED: {
                cls.PENDING, cls.SUGGESTED, cls.IN_PROGRESS,
                cls.DONE,
            },

            cls.ARCHIVED: set(),  # Estado Terminal
        }

    def can_transition_to(self, new_status: "TaskStatus") -> bool:
        """Check if a task can transition from the current status to a new status.

        Args:
            new_status (TaskStatus): Target status.

        Returns:
            bool: True if transition is valid, False otherwise.
        """

        # Allow same-status transitions as a no-op
        if self == new_status:
            return True

        transitions = self._get_transitions()
        return new_status in transitions[self]


class Priority(IntEnum):
    """Enumeration of priority levels for tasks or projects.

    Supports native Python comparison (e.g., Priority.CRITICAL > Priority.LOW).
    """

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    def __str__(self) -> str:
        return self.name.capitalize()


class RecurrenceInterval(StrEnum):
    """Enumeration of possible recurrence intervals for tasks."""
    HOURLY = "HO"
    DAILY = "DA"
    WEEKLY = "WE"
    MONTHLY = "MO"
    YEARLY = "YE"


class EnergyLevel(IntEnum):
    """Represents the cognitive or physical effort required for a task.

    Inspired by GTD (Getting Things Done) methodology.
    """

    DRAINED = 1         # "Zombie mode": only microtasks < 2 min
    LOW = 2             # Light administrative tasks
    BALANCED = 3        # Standard work, meetings
    HIGH = 4            # Serious focus, active production
    PEAK = 5            # "God Mode": complex problem-solving / Deep Work

    def __str__(self) -> str:
        return self.name.capitalize()


class TaskComplexity(IntEnum):
    """Represents the complexity level of a task."""

    VERY_LOW = 1
    LOW = 2
    MEDIUM = 3
    HIGH = 4
    VERY_HIGH = 5

    def __str__(self) -> str:
        return self.name.capitalize()


class MomentumTrend(StrEnum):
    """Represents the trend of user momentum in task execution."""

    RISING = "rising"           # User is "on fire", can handle higher complexity
    STABLE = "stable"           # Flow maintained
    FALLING = "falling"         # Fatigue warning, suggest easier tasks
    STAGNANT = "stagnant"       # Total inertia, needs a "Quick Win" (microtask)
