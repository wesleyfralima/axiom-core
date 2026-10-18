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
    """

    def __init__(self, task_id: str, title: str, since: datetime) -> None:
        super().__init__(
            f"The timer of '{title}' is running: pause it before starting another."
        )
        self.task_id: str = task_id
        self.title: str = title
        self.since: datetime = since
