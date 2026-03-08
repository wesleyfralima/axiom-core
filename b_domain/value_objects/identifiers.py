from dataclasses import dataclass

from a_core.base import UniqueId


@dataclass(frozen=True)
class TaskId(UniqueId):
    """Strong identifier for Tasks."""


@dataclass(frozen=True)
class UserId(UniqueId):
    """Strong identifier for Users."""


@dataclass(frozen=True)
class ContextId(UniqueId):
    """Strong identifier for Contexts."""


@dataclass(frozen=True)
class TimeEntryId(UniqueId):
    """Strong identifier for Time Tracking entries."""
