from dataclasses import dataclass
from typing import Optional

from a_core import DTO


@dataclass(frozen=True, kw_only=True)
class UserPrefsInputDTO(DTO):
    """Detailed user configuration settings."""

    # ------------------------------------------------------------------
    # Calendar & time
    # ------------------------------------------------------------------
    timezone: Optional[str] = None
    week_start: Optional[str] = None  # monday | sunday
    working_hours_start: Optional[int] = None
    working_hours_end: Optional[int] = None
    skip_weekends: Optional[bool] = None

    default_task_duration_minutes: Optional[int] = None

    # ------------------------------------------------------------------
    # Task behavior
    # ------------------------------------------------------------------
    default_task_priority: Optional[str] = None
    default_task_status: Optional[str] = None
    auto_schedule_tasks: Optional[bool] = None
    allow_overdue_tasks: Optional[bool] = None

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------
    notify_due_soon: Optional[bool] = None
    notify_overdue: Optional[bool] = None
    notify_task_completed: Optional[bool] = None

    daily_summary_enabled: Optional[bool] = None
    daily_summary_time: Optional[str] = None  # HH:MM

    # ------------------------------------------------------------------
    # Recurrence & automation
    # ------------------------------------------------------------------
    auto_create_next_recurrence: Optional[bool] = None
    recurring_tasks_visible_ahead_days: Optional[int] = None

    # ------------------------------------------------------------------
    # Localization
    # ------------------------------------------------------------------
    language: Optional[str] = None
    date_format: Optional[str] = None
    time_format_24h: Optional[bool] = None

    # ------------------------------------------------------------------
    # UI/UX
    # ------------------------------------------------------------------
    theme: Optional[str] = None


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
    skip_weekends: bool

    default_task_duration_minutes: int

    # ------------------------------------------------------------------
    # Task behavior
    # ------------------------------------------------------------------
    default_task_priority: str
    default_task_status: str
    auto_schedule_tasks: bool
    allow_overdue_tasks: bool

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
    recurring_tasks_visible_ahead_days: int

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
