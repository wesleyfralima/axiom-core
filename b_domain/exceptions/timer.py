"""Why a timer cannot start: one runs already."""

from datetime import datetime

from a_core.exceptions import DomainException


class TimerRunningError(DomainException):
    """A timer is running — one at a time: it is paused before another
    starts (never on its own), so no time counts twice.

    Attributes:
        task_id (str): The task whose timer runs.
        title (str): Its title.
        since (datetime): When it started (an instant).
        forgotten (bool): It runs past the end of the day it started in.
        last_change (datetime | None): The user's last change after it
            started, that day (a hint of when they stopped).
    """

    def __init__(
        self,
        task_id: str,
        title: str,
        since: datetime,
        forgotten: bool = False,
        last_change: datetime | None = None,
    ) -> None:
        super().__init__(
            f"The timer of '{title}' is running: pause it before starting another."
        )
        self.task_id: str = task_id
        self.title: str = title
        self.since: datetime = since
        self.forgotten: bool = forgotten
        self.last_change: datetime | None = last_change


class TookPastTimerError(DomainException):
    """``done --took`` with a running timer: the timer would stop where
    the time told puts it, but that is after the task was done (or in the
    future) — the timer started later than the work did.

    Attributes:
        task_id (str): The task.
        title (str): Its title.
    """

    def __init__(self, task_id: str, title: str, message: str) -> None:
        super().__init__(message)
        self.task_id: str = task_id
        self.title: str = title
