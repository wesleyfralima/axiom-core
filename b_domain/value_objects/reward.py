class RewardModel:
    """Computes reward values for task outcomes.

    This model assigns positive or negative rewards based on whether
    a task was completed, skipped, or abandoned. It also incorporates
    task duration and complexity into the reward calculation.

    - Completed tasks yield positive rewards, scaled by duration and complexity
    - Skipped tasks incur a small penalty
    - Abandoned tasks incur a larger penalty
    """

    @staticmethod
    def task_reward(
        completed: bool,
        skipped: bool,
        abandoned: bool,
        duration: float,
        complexity: float,
    ) -> float:
        """Calculate the reward for a task outcome.

        Args:
            completed (bool): Whether the task was completed.
            skipped (bool): Whether the task was skipped.
            abandoned (bool): Whether the task was abandoned.
            duration (float): Duration of the task in minutes.
            complexity (float): Complexity level of the task.

        Returns:
            float: The computed reward value.
        """

        reward: float = 0.0

        if completed:
            reward += 1.0
            reward += duration * 0.02
            reward += complexity * 0.05

        if skipped:
            reward -= 0.3

        if abandoned:
            reward -= 0.8

        return reward
