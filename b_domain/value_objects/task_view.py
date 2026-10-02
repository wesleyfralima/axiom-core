"""A saved view: a name for a set of the task list's filters."""

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from b_domain.value_objects.identifiers import UserId

VIEW_NAME: re.Pattern[str] = re.compile(r"^[a-z0-9][a-z0-9_-]{0,29}$")
"""Lower case letters, digits, - and _, starting with a letter or digit, up
to 30 characters: ``urgent-work``."""


class ViewScope(StrEnum):
    """Where a view is seen."""

    # Only on the device that saved it (never synced)
    DEVICE = "device"
    # On every device of the account (synced)
    GLOBAL = "global"


@dataclass(frozen=True, kw_only=True)
class TaskView:
    """A saved view: the task list's filters under a name.

    The filters are the task list request's fields, as JSON (dates as typed
    — "today" stays relative —, a context by its name), so any interface
    can run them. A device's own view hides an account's one of the same
    name, there.

    Attributes:
        user_id (UserId): Whose.
        name (str): Its name (``VIEW_NAME``).
        scope (ViewScope): This device's, or every device's.
        filters (dict[str, Any]): The list's filters, by field.
        saved_at (datetime): When it was last saved.
    """

    user_id: UserId
    name: str
    scope: ViewScope
    filters: dict[str, Any] = field(compare=False)
    saved_at: datetime = field(compare=False)
