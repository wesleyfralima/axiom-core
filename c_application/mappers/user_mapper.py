from typing import overload

from b_domain.entities.user import User, UserPrefs
from c_application.dtos.user_dtos import (
    UserOutputDTO,
    UserPrefsInputDTO,
    UserPrefsOutputDTO,
)


class UserMapper[D: UserOutputDTO]:
    """Centralized mapper for User transformations.

    This class decouples the User Domain Entity from the application DTOs.
    It provides static methods to convert between domain entities and DTOs,
    ensuring a clean separation between layers.
    """

    # 1. When no dto_class is given,
    # retorna estritamente UserOutputDTO
    @overload
    @staticmethod
    def to_output(
        user: User,
    ) -> UserOutputDTO:
        pass

    # 2. When a specific dto_class (subclass)
    # is given, returns that subclass type
    @overload
    @staticmethod
    def to_output(
        user: User,
        *,
        dto_class: type[D],
    ) -> D:
        pass

    @staticmethod
    def to_output(
        user: User,
        *,
        dto_class: type[UserOutputDTO] = UserOutputDTO,
    ) -> UserOutputDTO:
        """Map a User entity to a UserOutputDTO.

        Args:
            user (User): The domain User entity to be mapped.
            dto_class (Type[TUserDTO], optional): The DTO class to instantiate.
                Defaults to UserOutputDTO.

        Returns:
            TUserDTO: A DTO containing user information suitable for presentation.
        """
        return dto_class(
            id=str(user.id),
            username=user.username,
            timezone=user.preferences.timezone,
            language=user.preferences.language,
        )

    @staticmethod
    def to_domain_prefs(dto: UserPrefsInputDTO) -> UserPrefs:
        """Convert a UserPrefsInputDTO into a UserPrefs Value Object.

        Args:
            dto (UserPrefsInputDTO): Input DTO containing user preference data.

        Returns:
            UserPrefs: A domain Value Object representing user preferences.

        Notes:
            - Fields with None values are ignored, allowing UserPrefs defaults
              to be applied automatically.
            - Language values are normalized to lowercase.
            - Timezone values could be validated against IANA identifiers.
        """
        data = {k: v for k, v in dto.__dict__.items() if v is not None}

        if "language" in data:
            data["language"] = data["language"].lower()

        if "timezone" in data:
            # Potential validation for IANA timezone identifiers could be added here
            pass

        return UserPrefs(**data)

    @staticmethod
    def prefs_from_entity(entity: User) -> UserPrefsOutputDTO:
        """Extract preferences from a User entity and map them to a DTO.

        Args:
            entity (User): The domain User entity containing preferences.

        Returns:
            UserPrefsOutputDTO: A DTO with user preference details for presentation.
        """
        prefs: UserPrefs = entity.preferences
        return UserPrefsOutputDTO(
            timezone=prefs.timezone,
            week_start=prefs.week_start,
            working_hours_start=prefs.working_hours_start,
            working_hours_end=prefs.working_hours_end,
            skip_weekends=prefs.skip_weekends,
            default_task_duration_minutes=prefs.default_task_duration_minutes,
            default_task_priority=prefs.default_task_priority,
            default_task_status=prefs.default_task_status,
            auto_schedule_tasks=prefs.auto_schedule_tasks,
            allow_overdue_tasks=prefs.allow_overdue_tasks,
            notify_due_soon=prefs.notify_due_soon,
            notify_overdue=prefs.notify_overdue,
            notify_task_completed=prefs.notify_task_completed,
            daily_summary_enabled=prefs.daily_summary_enabled,
            daily_summary_time=prefs.daily_summary_time,
            auto_create_next_recurrence=prefs.auto_create_next_recurrence,
            recurring_tasks_visible_ahead_days=prefs.recurring_tasks_visible_ahead_days,
            language=prefs.language,
            date_format=prefs.date_format,
            time_format_24h=prefs.time_format_24h,
            theme=prefs.theme,
        )
