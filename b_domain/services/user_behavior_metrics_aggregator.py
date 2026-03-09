from dataclasses import replace
from datetime import datetime

from b_domain.value_objects.enums import TaskComplexity, EnergyLevel
from b_domain.value_objects.reward import RewardModel
from b_domain.value_objects.user_behavior_metrics import UserBehaviorMetrics


class UserBehaviorMetricsAggregator:
    """Updates user behavior metrics based on task and session events.

    Provides static methods to record task completions, skips,
    abandonments, and rest periods, updating averages and totals
    in a new immutable `UserBehaviorMetrics` instance.
    """

    REST_THRESHOLD_MINUTES: int = 15

    @staticmethod
    def record_task_completed(
            metrics: UserBehaviorMetrics,
            duration_minutes: int,
            energy: EnergyLevel,
            complexity: TaskComplexity,
            now: datetime,
    ) -> UserBehaviorMetrics:
        """Records a completed task and updates averages.

        Args:
            metrics (UserBehaviorMetrics): Current metrics snapshot.
            duration_minutes (int): Duration of the completed task.
            energy (EnergyLevel): Energy level used for the task.
            complexity (TaskComplexity): Complexity level of the task.
            now (datetime): Timestamp of completion.

        Returns:
            UserBehaviorMetrics: Updated metrics with new averages and totals.
        """

        new_total: int = metrics.total_tasks_completed + 1

        # Weighted average update for task duration
        total_duration: float = (metrics.avg_task_duration_minutes * metrics.total_tasks_completed) + duration_minutes
        avg_duration: float = total_duration / new_total

        # Weighted average update for energy
        total_energy: float = (metrics.avg_energy_used * metrics.total_tasks_completed) + energy.value
        avg_energy: float = total_energy / new_total

        # Weighted average update for complexity
        total_complexity: float = (metrics.avg_task_complexity * metrics.total_tasks_completed) + complexity.value
        avg_complexity = total_complexity / new_total

        interval_avg: float = metrics.avg_completion_interval_minutes

        # If there was a previous completion, update average interval between completions
        if metrics.last_task_completion_at:
            gap: float = (now - metrics.last_task_completion_at).total_seconds() / 60
            previous_intervals: int = max(0, metrics.total_tasks_completed - 1)
            total_interval: float = (metrics.avg_completion_interval_minutes * previous_intervals) + gap
            new_intervals: int = previous_intervals + 1
            interval_avg: float = total_interval / new_intervals

        task_reward: float = RewardModel.task_reward(
            completed=True,
            skipped=False,
            abandoned=False,
            duration=duration_minutes,
            complexity=complexity.value,
        )

        total_reward: float = (metrics.avg_task_reward * metrics.total_tasks_completed) + task_reward
        avg_reward: float = total_reward / new_total

        return replace(
            metrics,
            total_tasks_completed=new_total,
            avg_task_duration_minutes=avg_duration,
            avg_energy_used=avg_energy,
            avg_task_complexity=avg_complexity,
            avg_completion_interval_minutes=interval_avg,
            last_task_completion_at=now,
            avg_task_reward=avg_reward,
        )

    @staticmethod
    def record_task_skipped(metrics: UserBehaviorMetrics) -> UserBehaviorMetrics:
        """Records a skipped task.

        Args:
            metrics (UserBehaviorMetrics): Current metrics snapshot.

        Returns:
            UserBehaviorMetrics: Updated metrics with incremented skip count.
        """
        return replace(
            metrics,
            total_tasks_skipped=metrics.total_tasks_skipped + 1
        )

    @staticmethod
    def record_task_abandoned(metrics: UserBehaviorMetrics) -> UserBehaviorMetrics:
        """Records an abandoned task.

        Args:
            metrics (UserBehaviorMetrics): Current metrics snapshot.

        Returns:
            UserBehaviorMetrics: Updated metrics with incremented abandon count.
        """
        return replace(
            metrics,
            total_tasks_abandoned=metrics.total_tasks_abandoned + 1
        )

    @staticmethod
    def record_rest(metrics: UserBehaviorMetrics, rest_duration_minutes: int) -> UserBehaviorMetrics:
        """Records a rest period and updates average rest duration.

        Args:
            metrics (UserBehaviorMetrics): Current metrics snapshot.
            rest_duration_minutes (int): Duration of the rest period in minutes.

        Returns:
            UserBehaviorMetrics: Updated metrics with new average rest duration.
        """

        # Rest averages are weighted by total completed + skipped tasks
        new_total: int = metrics.total_tasks_completed + metrics.total_tasks_skipped
        if new_total == 0:
            return metrics

        total_rest: float = metrics.avg_rest_minutes * (new_total - 1) + rest_duration_minutes
        avg_rest: float = total_rest / new_total

        return replace(
            metrics,
            avg_rest_minutes=avg_rest
        )

    @staticmethod
    def record_focus_block(metrics: UserBehaviorMetrics, focus_minutes: int) -> UserBehaviorMetrics:
        """Records a completed focus block and updates the average focus duration.

        Args:
            metrics (UserBehaviorMetrics): Current metrics snapshot.
            focus_minutes (int): Duration of the focus block in minutes.

        Returns:
            UserBehaviorMetrics: Updated metrics with new average focus duration.
        """

        if focus_minutes < 5:
            return metrics

        # Use number of focus blocks approximated by completed tasks
        total_focus: float = (metrics.avg_focus_block_minutes * metrics.total_focus_blocks) + focus_minutes

        new_blocks: int = metrics.total_focus_blocks + 1
        avg_focus: float = total_focus / new_blocks

        return replace(
            metrics,
            avg_focus_block_minutes=avg_focus,
            total_focus_blocks=new_blocks,
        )

    @staticmethod
    def record_focus_break(metrics: UserBehaviorMetrics) -> UserBehaviorMetrics:
        """Records an intentional break during a focus session."""
        return replace(
            metrics,
            total_focus_breaks=metrics.total_focus_breaks + 1,
        )

    @staticmethod
    def record_focus_abandon(metrics: UserBehaviorMetrics) -> UserBehaviorMetrics:
        """Records abandonment during a focus block."""
        return replace(
            metrics,
            total_focus_abandons=metrics.total_focus_abandons + 1
        )

    @staticmethod
    def record_pause(
            metrics: UserBehaviorMetrics,
            pause_minutes: int
    ) -> UserBehaviorMetrics:
        """Records an external pause (e.g., lunch, meeting)."""

        if pause_minutes <= 0:
            return metrics

        previous: int = metrics.total_pauses

        total_pause: float = (metrics.avg_pause_minutes * previous) + pause_minutes

        new_total: int = previous + 1
        avg_pause: float = total_pause / new_total

        return replace(
            metrics,
            total_pauses=new_total,
            avg_pause_minutes=avg_pause
        )

    @staticmethod
    def record_break(
            metrics: UserBehaviorMetrics,
            minutes: int
    ) -> UserBehaviorMetrics:

        if minutes <= UserBehaviorMetricsAggregator.REST_THRESHOLD_MINUTES:
            return UserBehaviorMetricsAggregator.record_rest(
                metrics,
                minutes
            )

        return UserBehaviorMetricsAggregator.record_pause(
            metrics,
            minutes
        )
