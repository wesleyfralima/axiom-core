"""Saved views: a name for a set of the task list's filters."""

from dataclasses import dataclass, field
from typing import Any

from a_core import DTO


@dataclass(frozen=True, kw_only=True)
class SaveTaskViewInputDTO(DTO):
    """Save a view.

    Attributes:
        user_id (str): Whose.
        name (str): Its name: lower case letters, digits, - and _ (up to 30).
        filters (dict[str, Any]): The task list's filters, by the field of
            ``ListTasksRequest`` (``user_id`` aside): dates as typed, a
            context by its name.
        everywhere (bool): Every device's (it syncs), not only this one's.
    """

    user_id: str
    name: str
    filters: dict[str, Any]
    everywhere: bool = False


@dataclass(frozen=True, kw_only=True)
class TaskViewInputDTO(DTO):
    """A view by its name.

    Attributes:
        user_id (str): Whose.
        name (str): Its name.
        everywhere (bool | None): Which one: every device's (True), this
            device's (False), or the one seen here (None: this device's
            wins over every device's of the same name).
    """

    user_id: str
    name: str
    everywhere: bool | None = None


@dataclass(frozen=True, kw_only=True)
class TaskViewsInputDTO(DTO):
    """The user's views."""

    user_id: str


@dataclass(frozen=True, kw_only=True)
class TaskViewOutputDTO(DTO):
    """A saved view.

    Attributes:
        name (str): Its name.
        everywhere (bool): Every device's (synced), or this device's.
        filters (dict[str, Any]): Its filters, by field.
        hidden (bool): Every device's, hidden here by this device's own of
            the same name.
        replaced (bool): Saving it replaced one of the same name and scope.
    """

    name: str
    everywhere: bool
    filters: dict[str, Any]
    hidden: bool = False
    replaced: bool = False


@dataclass(frozen=True, kw_only=True)
class TaskViewsOutputDTO(DTO):
    """The user's views: this device's first, then every device's, by name."""

    views: list[TaskViewOutputDTO] = field(default_factory=list)
