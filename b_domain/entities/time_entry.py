from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from a_core import Entity
from a_core.exceptions import DomainException
from b_domain.value_objects import TaskId, UserId


@dataclass(kw_only=True)
class TimeEntry(Entity):
    task_id: TaskId
    user_id: UserId
    start_time: datetime
    end_time: Optional[datetime] = None
    description: str = ""

    def elapsed_minutes(self, now: Optional[datetime] = None) -> int:

        if not now and not self.end_time:
            raise DomainException("`now` must be a valid `datetime` when there is no `end_time`")

        if not self.end_time:
            delta = now - self.start_time
        else:
            delta = self.end_time - self.start_time
        return int(delta.total_seconds() // 60)

    def stop(self, now: datetime):
        if self.end_time:
            raise DomainException("Timer already stopped.")
        self.end_time = now
