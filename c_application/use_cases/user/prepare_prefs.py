from dataclasses import dataclass

from a_core import DTO
from b_domain.entities import User
from b_domain.exceptions.user import UserNotFoundError
from b_domain.ports.use_case import UseCase
from c_application.dtos.user_dtos import UserPrefsOutputDTO
from c_application.mappers.user_mapper import UserMapper


@dataclass(frozen=True, kw_only=True)
class PrepareUserPreferencesInputDTO(DTO):
    """Input DTO for preparing user preferences for interactive configuration.

    Attributes:
        username (str): The username whose preferences will be prepared.
        timezone (str | None): The time zone the user is about to choose, for
            the holiday region suggestion (default: their current one).
    """

    username: str
    timezone: str | None = None


@dataclass(frozen=True, kw_only=True)
class PrepareUserPreferencesOutputDTO(DTO):
    """Output DTO for preparing user preferences input.

    Provides the current effective preferences of the user,
    suitable for pre-filling interactive forms.

    Attributes:
        preferences (UserPrefsOutputDTO): Fully resolved user preferences.
        suggested_holiday_region (str | None): With no holiday region set, the
            country the time zone points to, for the user to confirm.
        message (str): Status message confirming preparation.
            Defaults to "preferences_prepared".
    """

    preferences: UserPrefsOutputDTO
    suggested_holiday_region: str | None = None
    message: str = "preferences_prepared"


class PrepareUserPreferencesUseCase(
    UseCase[PrepareUserPreferencesInputDTO, PrepareUserPreferencesOutputDTO]
):
    """Prepare user preferences for interactive configuration.

    This use case retrieves the current effective preferences of a user,
    ensuring that defaults are already applied (via entity initialization),
    and returns them in a format suitable for UI/CLI forms.
    """

    async def execute(
        self,
        request: PrepareUserPreferencesInputDTO,
    ) -> PrepareUserPreferencesOutputDTO:
        async with self.uow as uow:
            user: User | None = await uow.users.get_by_username(request.username)
            if not user:
                raise UserNotFoundError(request.username)

            prefs_dto: UserPrefsOutputDTO = UserMapper.prefs_from_entity(user)
            suggested: str | None = (
                None
                if prefs_dto.holiday_region
                else uow.holidays.region_for_timezone(
                    request.timezone or prefs_dto.timezone
                )
            )

        return PrepareUserPreferencesOutputDTO(
            preferences=prefs_dto,
            suggested_holiday_region=suggested,
        )
