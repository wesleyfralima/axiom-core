from dataclasses import dataclass

from a_core import DTO
from b_domain.entities.user import User
from b_domain.exceptions.user import UserNotFoundError
from b_domain.ports.use_case import UseCase
from c_application.dtos.user_dtos import UserPrefsOutputDTO
from c_application.mappers.user_mapper import UserMapper


@dataclass(frozen=True, kw_only=True)
class GetUserPreferencesInputDTO(DTO):
    """Input DTO for retrieving user preferences.

    Encapsulates the username of the user whose preferences
    should be fetched.

    Attributes:
        username (str): The username of the user whose preferences will be retrieved.
    """

    username: str


@dataclass(frozen=True, kw_only=True)
class GetUserPreferencesOutputDTO(DTO):
    """Output DTO for user preference retrieval responses.

    Represents the current preferences of a user after a successful
    retrieval operation.

    Attributes:
        username (str): The username of the user.
        preferences (UserPrefsOutputDTO): DTO containing the user's preferences.
        message (str): Status message confirming the retrieval.
            Defaults to "preferences_retrieved".
    """

    username: str
    preferences: UserPrefsOutputDTO
    message: str = "preferences_retrieved"


class GetUserPreferencesUseCase(
    UseCase[GetUserPreferencesInputDTO, GetUserPreferencesOutputDTO]
):
    """Use case for retrieving user preferences."""

    async def execute(
        self, request: GetUserPreferencesInputDTO
    ) -> GetUserPreferencesOutputDTO:
        """Execute the preference retrieval workflow.

        Steps:
            1. Retrieve the user aggregate by username.
            2. Map the user's preferences to an output DTO.

        Args:
            request (GetUserPreferencesInputDTO): Request object containing
                the username whose preferences should be retrieved.

        Returns:
            GetUserPreferencesOutputDTO: Output DTO representing the user's preferences.

        Raises:
            UserNotFoundError: If the user does not exist.
        """

        async with self.uow as uow:
            # 1. Retrieve user aggregate
            user: User | None = await uow.users.get_by_username(request.username)
            if not user:
                raise UserNotFoundError(request.username)

            # 2. Centralized output mapping
            return GetUserPreferencesOutputDTO(
                username=user.username,
                preferences=UserMapper.prefs_from_entity(user),
            )
