from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from b_domain.entities import Task


class CalendarEventVisibility(str, Enum):
    """Enumeration for event visibility values.

    Attributes:
        DEFAULT (str): Provider default visibility.
        PUBLIC (str): Event is visible to everyone.
        PRIVATE (str): Event is restricted to the owner.
    """
    DEFAULT = "default"
    PUBLIC = "public"
    PRIVATE = "private"


class CalendarEventStatus(str, Enum):
    """Enumeration for event status values.

    Attributes:
        CONFIRMED (str): Event is confirmed.
        TENTATIVE (str): Event is tentative.
        CANCELLED (str): Event is cancelled.
    """
    CONFIRMED = "confirmed"
    TENTATIVE = "tentative"
    CANCELLED = "cancelled"


@dataclass
class CalendarEventAttendee:
    """Represents an event attendee.

    Attributes:
        email (str): Attendee's email address.
        response_status (str): Response status of the attendee.
            Possible values: "accepted", "declined", "needsAction".
            Defaults to "needsAction".
        optional (bool): Indicates if the attendee is optional.
            Defaults to False.
    """
    email: str
    response_status: str = "needsAction"  # Default response status
    optional: bool = False  # Whether the attendee is optional


@dataclass
class CalendarEventInput:
    """Data for creating or updating an event.

    All optional fields allow partial updates (PATCH).
    On creation, `start` and `end` must be validated as required
    by the service layer.

    Attributes:
        summary (Optional[str]): Event summary or title.
        start (Optional[datetime]): Start date and time of the event.
        end (Optional[datetime]): End date and time of the event.
        description (Optional[str]): Event description.
        location (Optional[str]): Event location.
        attendees (list[CalendarEventAttendee]): List of attendees.
        recurrence_rules (list[str]): Recurrence rules in RFC5545 format.
        reminders_enabled (bool): Whether reminders are enabled.
        color_id (Optional[str]): Color identifier for the event.
        visibility (CalendarEventVisibility): Event visibility.
    """

    summary: Optional[str] = None
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    description: Optional[str] = None
    location: Optional[str] = None
    attendees: list[CalendarEventAttendee] = field(default_factory=list)
    recurrence_rules: list[str] = field(default_factory=list)
    reminders_enabled: bool = True
    color_id: Optional[str] = None
    visibility: CalendarEventVisibility = CalendarEventVisibility.DEFAULT

    @staticmethod
    def from_task(task: Task, duration_minutes: int = 60) -> "CalendarEventInput":
        """Build a CalendarEventInput from a Task entity.

        Args:
            task (Task): The task entity to export.
            duration_minutes (int): Default duration in minutes.

        Returns:
            CalendarEventInput: Input object ready for provider integration.
        """

        # 1. Determine the base start date
        # If recurrence exists, use the first valid occurrence
        if task.recurrence:
            first_valid_occurrence = task.recurrence.get_next_occurrence()
            start = first_valid_occurrence or task.recurrence.start_date
        elif task.due_date.value:
            start = task.due_date.value
        else:
            start = task.created_at

        # 2. Ensure UTC timezone
        if start.tzinfo is None:
            from datetime import timezone
            start = start.replace(tzinfo=timezone.utc)

        # 3. Define end time based on duration
        end = start + timedelta(minutes=duration_minutes)

        # 4. Convert recurrence to RFC5545 format if supported
        rrules: list[str] = []
        if task.recurrence:
            # Only include RRULE if provider supports native sync
            if task.recurrence.supports_native_sync():
                rrules.append(task.recurrence.rrule_string)

        return CalendarEventInput(
            summary=task.title.value,
            description=task.description.value,
            start=start,
            end=end,
            recurrence_rules=rrules,
        )


@dataclass
class CalendarEventOutput:
    """Represents an event already persisted in the provider.

    Extends EventInput with additional metadata fields.

    Attributes:
        id (str): Unique identifier of the event.
        calendar_id (str): Reference to the parent calendar.
        html_link (str): Link to open the event in a browser.
        status (CalendarEventStatus): Event status.
        created_at (Optional[datetime]): Timestamp when the event was created.
        updated_at (Optional[datetime]): Timestamp when the event was last updated.
        creator_email (Optional[str]): Email of the event creator.
        start (datetime): Start date and time (guaranteed non-null in output).
        end (datetime): End date and time (guaranteed non-null in output).
    """

    id: str = ""  # Unique identifier of the event
    calendar_id: str = ""  # Reference to parent calendar
    html_link: str = ""  # Browser link to view event
    status: CalendarEventStatus = CalendarEventStatus.CONFIRMED
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    creator_email: Optional[str] = None

    # Start and end are guaranteed non-null in output
    start: datetime = field(default_factory=datetime.now)
    end: datetime = field(default_factory=datetime.now)


class CalendarProvider(ABC):
    """Abstract contract for managing calendars and events.

    Any integration (Google, Outlook, Local) must inherit and implement this class.
    """

    @abstractmethod
    async def create_event(self, calendar_id: str, event_data: CalendarEventInput) -> CalendarEventOutput:
        """Insert a new event into a calendar.

        Args:
            calendar_id (str): The calendar identifier.
            event_data (CalendarEventInput): Input data for the new event.

        Returns:
            CalendarEventInput: The object with information about the created event.
        """

    @abstractmethod
    async def delete_event(self, calendar_id: str, event_id: str) -> bool:
        """Delete (cancel) an event.

        Args:
            calendar_id (str): The calendar identifier.
            event_id (str): The event identifier.

        Returns:
            bool: True if the event was deleted successfully, False otherwise.
        """

    @abstractmethod
    async def get_event(self, calendar_id: str, event_id: str) -> Optional[CalendarEventOutput]:
        """Retrieve a single event by its ID.

        Args:
            calendar_id (str): The calendar identifier.
            event_id (str): The event identifier.

        Returns:
            Optional[CalendarEventOutput]: The event object if found, otherwise None.
        """
