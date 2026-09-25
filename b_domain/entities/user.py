"""User entity and preferences definitions for the domain."""

from dataclasses import dataclass, field, fields, replace
from datetime import datetime
from typing import Any, ClassVar, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from a_core import Entity, ValueObject
from a_core.exceptions import (
    DomainException,
    InvalidValueError,
    ValidationException,
)
from b_domain.value_objects import UserId
from b_domain.value_objects.enums import Priority
from b_domain.value_objects.identifiers import ContextId


@dataclass(frozen=True, kw_only=True)
class UserPrefs(ValueObject):
    """Value object representing user preferences.

    This is a frozen dataclass because preferences are conceptually
    a single immutable value. To update preferences, a new instance
    should be created.
    """

    _ALLOWED_KEYS: ClassVar[set[str]] = set()

    # ------------------------------------------------------------------
    # Calendar & time
    # ------------------------------------------------------------------
    timezone: str = "UTC"
    week_start: Literal["monday", "sunday"] = "monday"
    working_hours_start: int = 9  # 09:00
    working_hours_end: int = 18  # 18:00
    skip_weekends: bool = True
    external_calendar_name: str = "Axiom Pro"
    external_calendar_id: str | None = None
    external_calendar_autosync: bool = True

    # ------------------------------------------------------------------
    # Task behavior
    # ------------------------------------------------------------------
    default_task_duration_minutes: int = 60
    default_task_priority: str = "medium"
    default_task_status: str = "pending"
    auto_schedule_tasks: bool = False
    allow_overdue_tasks: bool = True

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------
    notify_due_soon: bool = True
    notify_overdue: bool = True
    notify_task_completed: bool = False

    daily_summary_enabled: bool = False
    daily_summary_time: str = "08:00"

    # ------------------------------------------------------------------
    # General UI/System
    # ------------------------------------------------------------------
    theme: Literal["light", "dark", "system"] = "system"
    auto_create_next_recurrence: bool = True
    recurring_tasks_visible_ahead_days: int = 14
    language: str = "en"
    date_format: str = "YYYY-MM-DD"
    time_format_24h: bool = True

    # ------------------------------------------------------------------
    # Contexts
    # ------------------------------------------------------------------
    active_context_id: ContextId | None = None

    def __post_init__(self) -> None:
        if not UserPrefs._ALLOWED_KEYS:
            UserPrefs._ALLOWED_KEYS = {f.name for f in fields(self)}

    def update(self, **changes: Any) -> "UserPrefs":
        """Creates a new UserPrefs instance with the updated values.

        Args:
            **changes: Arbitrary keyword arguments representing the
                preferences to update.

        Returns:
            UserPrefs: A new instance with the merged preferences.
        """

        invalid_keys: set[str] = {k for k in changes if k not in self._ALLOWED_KEYS}

        if invalid_keys:
            raise ValidationException(
                f"Invalid fields for UserPrefs: {', '.join(invalid_keys)}"
            )

        return replace(self, **self._normalized(changes))

    @staticmethod
    def _normalized(changes: dict[str, Any]) -> dict[str, Any]:
        """Validate the preferences that only accept some values.

        Raises:
            InvalidValueError: If a value is not one the preference accepts.
        """

        result: dict[str, Any] = dict(changes)

        if "default_task_priority" in result:
            result["default_task_priority"] = Priority.parse(
                result["default_task_priority"]
            ).name.lower()

        if "timezone" in result:
            try:
                ZoneInfo(str(result["timezone"]))
            except (ZoneInfoNotFoundError, ValueError) as e:
                raise InvalidValueError(
                    concept="time zone", invalid_value=str(result["timezone"])
                ) from e

        for key, options in _CHOICES.items():
            if key in result:
                value: str = str(result[key]).strip().lower()
                if value not in options:
                    raise InvalidValueError(
                        concept=key.replace("_", " "),
                        invalid_value=str(result[key]),
                        valid_options=list(options),
                    )
                result[key] = value

        for key in ("working_hours_start", "working_hours_end"):
            if key in result and not 0 <= int(result[key]) <= 23:
                raise InvalidValueError(
                    concept=key.replace("_", " "), invalid_value=str(result[key])
                )

        return result


_CHOICES: dict[str, tuple[str, ...]] = {
    "week_start": ("monday", "sunday"),
    "theme": ("light", "dark", "system"),
}


@dataclass(kw_only=True, eq=False)
class User(Entity):
    """Represents a User entity within the domain.

    Inherits `id`, `created_at`, and `updated_at` from the base `Entity`.
    """

    id: "UserId" = field(default_factory=lambda: UserId())

    username: str
    email: str
    password_hash: str | None = None
    is_active: bool = True

    preferences: UserPrefs = field(default_factory=UserPrefs)

    @classmethod
    def create(
        cls,
        username: str,
        email: str,
        password_hash: str | None = None,
        is_active: bool = True,
        preferences: UserPrefs | None = None,
        now: datetime | None = None,
    ) -> "User":
        """Factory method to create a new User.

        Args:
            username (str): The unique username of the user.
            email (str): The unique email of the user.
            password_hash (Optional[str], optional): Hashed password. Defaults to None.
            is_active (bool, optional): Whether the user is active. Default: True.
            preferences (Optional[UserPrefs], optional): Initial preferences.
                Defaults to an empty UserPrefs instance.
            now (Optional[datetime], optional): Current timestamp. If not provided,
                the base Entity will automatically generate it in UTC.

        Returns:
            User: A new User instance.
        """

        clean_username: str = username.strip()
        if not clean_username:
            raise ValidationException("Username cannot be empty or whitespace.")

        clean_email: str = email.strip().lower()
        if not clean_email:
            raise ValidationException("Email cannot be empty or whitespace.")

        user: User = cls(
            username=clean_username,
            email=clean_email,
            password_hash=password_hash,
            is_active=is_active,
            preferences=preferences or UserPrefs(),
        )

        # If a specific timestamp is provided (e.g., for testing), inject it
        if now:
            object.__setattr__(user, "created_at", now)
            object.__setattr__(user, "updated_at", now)

        return user

    def update_prefs(self, now: datetime, **changes: Any) -> None:
        """Updates the user's preferences and refreshes the updated_at timestamp.

        Args:
            now (datetime): The current timestamp.
            **changes: The preference attributes to modify.
        """
        self.preferences = self.preferences.update(**changes)
        self._touch(now)

    def change_password(self, new_hash: str, now: datetime) -> None:
        """Business logic for changing a password."""
        if not new_hash:
            raise DomainException("Password hash cannot be empty.")
        self.password_hash = new_hash
        self._touch(now)

    def deactivate(self, now: datetime) -> None:
        """Business logic for deactivating a user account."""
        self.is_active = False
        self._touch(now)

    def activate(self, now: datetime) -> None:
        """Business logic for reactivating a user account."""
        self.is_active = True
        self._touch(now)
