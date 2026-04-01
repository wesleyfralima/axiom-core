from dataclasses import dataclass
from typing import Any, Dict

from a_core import DTO
from a_core.exceptions import DomainException
from b_domain.entities.user import User
from b_domain.ports.use_case import UseCase
from c_application.dtos.user_dtos import UserPrefsInputDTO, UserPrefsOutputDTO
from c_application.mappers.user_mapper import UserMapper


@dataclass(frozen=True, kw_only=True)
class UpdateUserPreferencesInputDTO(DTO):
    """Input DTO for updating user preferences.

    Encapsulates the username and a partial set of preferences
    to be updated. Fields set to None are ignored, allowing
    partial updates without overwriting existing values.

    Attributes:
        username (str): The username of the user whose preferences will be updated.
        preferences (UserPrefsInputDTO): DTO containing partial preference updates.
    """
    username: str
    preferences: UserPrefsInputDTO


@dataclass(frozen=True, kw_only=True)
class UpdateUserPreferencesOutputDTO(DTO):
    """Output DTO for user preferences update responses.

    Represents the updated preferences of a user after a successful
    update operation.

    Attributes:
        username (str): The username of the updated user.
        preferences (UserPrefsOutputDTO): DTO containing the updated preferences.
        message (str): Status message confirming the update.
            Defaults to "preferences_updated".
    """
    username: str
    preferences: UserPrefsOutputDTO
    message: str = "preferences_updated"


class UpdateUserPreferencesUseCase(UseCase[UpdateUserPreferencesInputDTO, UpdateUserPreferencesOutputDTO]):
    """Use case for updating user preferences.

    Handles partial updates to user settings, ensuring that only
    provided fields are changed while keeping others intact.
    """

    async def execute(self, request: UpdateUserPreferencesInputDTO) -> UpdateUserPreferencesOutputDTO:
        """Execute the preference update workflow.

        Steps:
            1. Retrieve the user aggregate by username.
            2. Filter out None values to allow partial updates.
            3. Delegate preference update logic to the User entity.
            4. Persist the updated user entity.
            5. Map the updated entity to an output DTO.

        Args:
            request (UpdateUserPreferencesInputDTO): Request object containing
                the username and partial preferences to update.

        Returns:
            UpdateUserPreferencesOutputDTO: Output DTO representing the updated user.

        Raises:
            DomainException: If the user does not exist.
        """

        async with self.uow as uow:

            # 1. Retrieve user aggregate
            user: User = await uow.users.get_by_username(request.username)
            if not user:
                raise DomainException(f"User '{request.username}' not found.")

            # 2. Prepare partial changes
            changes: Dict[str, Any] = {
                k: v for k, v in request.preferences.__dict__.items()
                if v is not None
            }

            # 3. Domain logic delegated to entity
            user.update_prefs(
                now=self.clock.now(),
                **changes
            )

            # 4. Persistence
            await uow.users.update(user)

        # 5. Centralized output mapping
        return UpdateUserPreferencesOutputDTO(
            username=user.username,
            preferences=UserMapper.prefs_from_entity(user),
        )
