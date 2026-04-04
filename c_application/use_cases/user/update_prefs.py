from dataclasses import asdict, dataclass
from typing import Any, Dict

from a_core import DTO
from a_core.exceptions import InvalidValueError, ValidationException
from b_domain.entities.user import User
from b_domain.exceptions.user import UserNotFoundError
from b_domain.ports.use_case import UseCase
from c_application.dtos.user_dtos import PreferenceChangeDTO, UserPrefsInputDTO, UserPrefsOutputDTO
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
    update operation, including details of what changed.

    Attributes:
        username (str): The username of the updated user.
        preferences (UserPrefsOutputDTO): DTO containing the updated preferences.
        changes (list[PreferenceChangeDTO]): A list of preference changes applied
            during the update, capturing old and new values for traceability.
        message (str): Status message confirming the update.
            Defaults to "preferences_updated".
    """
    username: str
    preferences: UserPrefsOutputDTO
    changes: list[PreferenceChangeDTO]
    message: str = "preferences_updated"


class UpdateUserPreferencesUseCase(UseCase[UpdateUserPreferencesInputDTO, UpdateUserPreferencesOutputDTO]):
    """Use case for updating user preferences.

    Handles partial updates to user settings, ensuring that only
    provided fields are changed while keeping others intact.
    Also computes a detailed list of changes applied for auditing
    and feedback purposes.
    """

    async def execute(self, request: UpdateUserPreferencesInputDTO) -> UpdateUserPreferencesOutputDTO:
        """Execute the preference update workflow.

        Steps:
            1. Retrieve the user aggregate by username.
            2. Extract non-None values from the request to allow partial updates.
            3. Delegate preference update logic to the User entity.
            4. Persist the updated user entity.
            5. Compute a diff of old vs. new values to produce a list of changes.
            6. Map the updated entity and changes to an output DTO.

        Args:
            request (UpdateUserPreferencesInputDTO): Request object containing
                the username and partial preferences to update.

        Returns:
            UpdateUserPreferencesOutputDTO: Output DTO representing the updated user
            and the list of applied preference changes.

        Raises:
            UserNotFoundError: If the user does not exist.
            ValidationException: If no preferences were provided to update.
            InvalidValueError: If a provided preference value is invalid.
        """

        async with self.uow as uow:

            # 1. Retrieve user aggregate
            user: User = await uow.users.get_by_username(request.username)
            if not user:
                raise UserNotFoundError(request.username)

            # 2. Prepare partial changes
            changes: Dict[str, Any] = {
                k: v for k, v in asdict(request.preferences).items()
                if v is not None
            }

            if not changes:
                raise ValidationException("No preferences were provided to update.")

            # Snapshot BEFORE state
            before: UserPrefsOutputDTO = UserMapper.prefs_from_entity(user)

            # 3. Domain logic delegated to entity
            try:
                user.update_prefs(
                    now=self.clock.now(),
                    **changes
                )
            except ValueError as e:
                raise InvalidValueError(concept="Preference Value", invalid_value=str(e))

            # Snapshot AFTER state
            after: UserPrefsOutputDTO = UserMapper.prefs_from_entity(user)

            # Compute diff
            computed_changes: list[PreferenceChangeDTO] = []

            for field in changes.keys():

                if not hasattr(before, field):
                    raise ValidationException(
                        f"Invalid preference field '{field}' not present in output DTO"
                    )

                old_value = getattr(before, field)
                new_value = getattr(after, field)

                if old_value != new_value:
                    computed_changes.append(
                        PreferenceChangeDTO(
                            field=field,
                            old_value=old_value,
                            new_value=new_value,
                        )
                    )

            # 4. Persistence
            await uow.users.update(user)

        # 5. Centralized output mapping
        return UpdateUserPreferencesOutputDTO(
            username=user.username,
            preferences=after,
            changes=computed_changes,
        )
