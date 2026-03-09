from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from a_core.base import ValueObject
from b_domain.value_objects import UserId


@dataclass(frozen=True, kw_only=True)
class UserBehaviorMetrics(ValueObject):
    """Aggregated metrics observed from user behavior.

    These metrics are derived from the user's interaction with the system
    over time. They capture task activity, energy usage, complexity,
    focus dynamics, and recovery patterns.

    Attributes:
        user_id (UserId): Identifier of the user these metrics belong to.
        total_tasks_completed (int): Total number of tasks completed.
        total_tasks_skipped (int): Total number of tasks skipped.
        total_tasks_abandoned (int): Total number of tasks abandoned.
        avg_task_duration_minutes (float): Average observed task duration in minutes.
        avg_energy_used (float): Average energy level used across tasks.
        avg_task_complexity (float): Average observed complexity of tasks.
        avg_focus_block_minutes (float): Average duration of focus blocks in minutes.
        avg_rest_minutes (float): Average duration of rest periods in minutes.
        avg_completion_interval_minutes (float): Average interval between task completions in minutes.
        last_task_completion_at (Optional[datetime]): Timestamp of the last task completion.
    """

    user_id: UserId

    # -------------------------------
    # Task activity metrics
    # -------------------------------
    total_tasks_completed: int = 0
    total_tasks_skipped: int = 0
    total_tasks_abandoned: int = 0

    # -------------------------------
    # Duration metrics
    # -------------------------------
    avg_task_duration_minutes: float = 0.0

    # -------------------------------
    # Energy metrics
    # -------------------------------
    avg_energy_used: float = 0.0

    # -------------------------------
    # Complexity metrics
    # -------------------------------
    avg_task_complexity: float = 0.0

    # -------------------------------
    # Focus dynamics
    # -------------------------------
    avg_focus_block_minutes: float = 0.0

    # -------------------------------
    # Recovery metrics
    # -------------------------------
    avg_rest_minutes: float = 0.0

    # -------------------------------
    # Momentum behavior
    # -------------------------------
    avg_completion_interval_minutes: float = 0.0

    # -------------------------------
    # Internal control
    # -------------------------------
    last_task_completion_at: Optional[datetime] = None
