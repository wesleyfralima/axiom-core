"""Why a snooze is refused."""

from datetime import datetime
from enum import StrEnum

from a_core.exceptions import DomainException


class SnoozeRefusal(StrEnum):
    """The reasons a task cannot be snoozed."""

    CLOSED = "closed"  # done, cancelled or archived
    NO_DUE = "no_due"  # nothing to put off
    NOT_DUE_YET = "not_due_yet"  # due after today: an edit moves it
    NOT_LATER = "not_later"  # the new moment is not after the due date or now
    LANDS_ON_NEXT = "lands_on_next"  # on the next occurrence's day, or later


class SnoozeRefusedError(DomainException):
    """A snooze the rules refuse; ``reason`` says which, so an interface can
    say what to do instead (an edit, keeping both, skipping this one).

    Attributes:
        reason (SnoozeRefusal): Why.
        next_due (datetime | None): The next occurrence's due date, when the
            snoozed one would land on it.
    """

    def __init__(
        self, reason: SnoozeRefusal, message: str, next_due: datetime | None = None
    ) -> None:
        super().__init__(message)
        self.reason: SnoozeRefusal = reason
        self.next_due: datetime | None = next_due
