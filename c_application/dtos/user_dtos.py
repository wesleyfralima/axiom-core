from dataclasses import dataclass
from typing import Any

from a_core import DTO


@dataclass(frozen=True, kw_only=True)
class PreferenceChangeDTO(DTO):
    """DTO representing a single preference change.

    Captures the details of a modification applied to a user's preferences,
    including the specific field that changed and its old/new values.
    Useful for auditing, logging, and providing feedback to the user.

    Attributes:
        field (str): The name of the preference field that was updated.
        old_value (Any): The previous value of the preference before the update.
        new_value (Any): The new value of the preference after the update.
    """

    field: str
    old_value: Any
    new_value: Any


@dataclass(frozen=True, kw_only=True)
class UserPrefsInputDTO(DTO):
    """Detailed user configuration settings."""

    # ------------------------------------------------------------------
    # Calendar & time
    # ------------------------------------------------------------------
    timezone: str | None = None
    week_start: str | None = None  # monday | sunday
    working_hours_start: int | None = None
    working_hours_end: int | None = None
    work_days: str | None = None  # mon,tue,… or a range (mon-fri)
    holiday_region: str | None = None  # BR, BR-SP…; "none" for no holidays
    skipped_holidays: str | None = None  # names, "; " between them

    default_task_duration_minutes: int | None = None

    # ------------------------------------------------------------------
    # Task behavior
    # ------------------------------------------------------------------
    default_task_priority: str | None = None
    default_task_status: str | None = None
    default_due_time: str | None = None  # HH:MM
    auto_schedule_tasks: bool | None = None
    allow_overdue_tasks: bool | None = None
    keep_deleted_days: int | None = None
    postpone_warnings: bool | None = None

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------
    notify_due_soon: bool | None = None
    notify_overdue: bool | None = None
    notify_task_completed: bool | None = None

    daily_summary_enabled: bool | None = None
    daily_summary_time: str | None = None  # HH:MM

    # ------------------------------------------------------------------
    # Recurrence & automation
    # ------------------------------------------------------------------
    auto_create_next_recurrence: bool | None = None
    days_ahead: int | None = None

    # ------------------------------------------------------------------
    # Localization
    # ------------------------------------------------------------------
    language: str | None = None
    date_format: str | None = None
    time_format_24h: bool | None = None

    # ------------------------------------------------------------------
    # UI/UX
    # ------------------------------------------------------------------
    theme: str | None = None


@dataclass(frozen=True, kw_only=True)
class UserPrefsOutputDTO(DTO):
    """Detailed user configuration settings."""

    # ------------------------------------------------------------------
    # Calendar & time
    # ------------------------------------------------------------------
    timezone: str
    week_start: str  # monday | sunday
    working_hours_start: int
    working_hours_end: int
    work_days: str  # mon,tue,wed,thu,fri
    holiday_region: str  # "" when none
    skipped_holidays: str  # the region's holidays worked anyway ("a; b")

    default_task_duration_minutes: int

    # ------------------------------------------------------------------
    # Task behavior
    # ------------------------------------------------------------------
    default_task_priority: str
    default_task_status: str
    default_due_time: str  # HH:MM
    auto_schedule_tasks: bool
    allow_overdue_tasks: bool
    keep_deleted_days: int
    postpone_warnings: bool

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------
    notify_due_soon: bool
    notify_overdue: bool
    notify_task_completed: bool

    daily_summary_enabled: bool
    daily_summary_time: str  # HH:MM

    # ------------------------------------------------------------------
    # Recurrence & automation
    # ------------------------------------------------------------------
    auto_create_next_recurrence: bool
    days_ahead: int

    # ------------------------------------------------------------------
    # Localization
    # ------------------------------------------------------------------
    language: str
    date_format: str
    time_format_24h: bool

    # ------------------------------------------------------------------
    # UI/UX
    # ------------------------------------------------------------------
    theme: str


@dataclass
class UserOutputDTO(DTO):
    """Public representation of a user and their key preferences."""

    # Basic
    id: str
    username: str

    # UX essentials
    timezone: str
    language: str
