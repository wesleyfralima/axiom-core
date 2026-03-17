from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from a_core import Entity
from a_core.exceptions import DomainException
from b_domain.value_objects import TaskId, UserId


@dataclass(kw_only=True, eq=False)
class TimeEntry(Entity):
    """Represents a tracked time interval for a task.

    A time entry records when a user started working on a task,
    when they stopped (if applicable), and optional descriptive notes.

    Attributes:
        task_id (TaskId): Identifier of the task being tracked.
        user_id (UserId): Identifier of the user who owns this entry.
        start_time (datetime): Timestamp when the task work started.
        end_time (Optional[datetime]): Timestamp when the task work ended.
            If None, the task is still in progress.
        description (str): Optional notes about the work session.
    """

    task_id: TaskId
    user_id: UserId
    start_time: datetime
    end_time: Optional[datetime] = None
    description: str = ""

    def elapsed_minutes(self, now: Optional[datetime] = None) -> int:
        """Calculate the elapsed time in minutes.

        If the entry has an `end_time`, the duration is measured between
        `start_time` and `end_time`. If the entry is still running, the
        duration is measured between `start_time` and the provided `now`.

        Args:
            now (Optional[datetime]): Current timestamp, required if
                `end_time` is not set.

        Returns:
            int: Elapsed time in minutes.

        Raises:
            DomainException: If `end_time` is not set and `now` is missing.
        """

        if not now and not self.end_time:
            raise DomainException("`now` must be a valid `datetime` when there is no `end_time`")

        delta: timedelta

        if not self.end_time:
            delta = now - self.start_time
        else:
            delta = self.end_time - self.start_time

        return int(delta.total_seconds() // 60)

    def stop(self, now: datetime):
        """Stop the timer by setting the `end_time`.

        Args:
            now (datetime): Timestamp when the task work stopped.

        Raises:
            DomainException: If the timer has already been stopped.
        """

        if self.end_time:
            raise DomainException("Timer already stopped.")

        self.end_time = now
