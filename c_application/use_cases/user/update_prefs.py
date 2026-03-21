from typing import Any, Dict

from a_core.exceptions import DomainException
from b_domain.entities.user import User
from b_domain.ports.use_case import UseCase
from c_application.dtos.user_dtos import UserOutputDTO, UserPrefsInputDTO, UpdateUserPreferencesRequest
from c_application.mappers.user_mapper import UserMapper


class UpdateUserPreferencesUseCase(UseCase[UserPrefsInputDTO, UserOutputDTO]):
    """Use case for updating user preferences.

    Handles partial updates to user settings, ensuring that only
    provided fields are changed while keeping others intact.
    """

    async def execute(self, request: UpdateUserPreferencesRequest) -> UserOutputDTO:
        """Execute the preference update workflow.

        Steps:
            1. Retrieve the user aggregate by username.
            2. Filter out None values to allow partial updates.
            3. Delegate preference update logic to the User entity.
            4. Persist the updated user entity.
            5. Map the updated entity to an output DTO.

        Args:
            request (UpdateUserPreferencesRequest): Request object containing
                the username and partial preferences to update.

        Returns:
            UserOutputDTO: Output DTO representing the updated user.

        Raises:
            DomainException: If the user does not exist.
        """

        async with self.uow as uow:

            # 1. Retrieve user aggregate
            user: User = await uow.users.get_by_username(request.username)
            if not user:
                raise DomainException(f"User '{request.username}' not found.")

            # 2. Prepare partial changes
            # Filter out None values to allow partial DTO updates
            changes: Dict[str, Any] = {
                k: v for k, v in request.preferences.__dict__.items()
                if v is not None
            }

            # 3. Domain logic delegated to entity
            # User entity internally creates a new UserPrefs via replace()
            user.update_prefs(
                now=self.clock.now(),
                **changes
            )

            # 4. Persistence
            # Repository saves the full state of preferences
            await uow.users.update(user)

        # 5. Centralized output mapping
        return UserMapper.to_output(user)
