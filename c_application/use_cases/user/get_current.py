from dataclasses import dataclass, field
from typing import Optional, Dict

from a_core import DTO
from b_domain.entities import User
from b_domain.exceptions.security import ExpiredTokenError, InvalidTokenError
from b_domain.ports.providers import ClockProvider, TokenProvider
from b_domain.ports.unity_of_work import UnitOfWork
from b_domain.ports.use_case import UowFactoryType, UseCase
from c_application.dtos.user_dtos import UserOutputDTO
from c_application.mappers.user_mapper import UserMapper


@dataclass(frozen=True)
class GetCurrentUserInputDTO(DTO):
    """Input DTO for retrieving the current user.

    Encapsulates the raw JWT token provided by the client,
    ensuring it adheres to the Use Case input contract.

    Attributes:
        token (str): The raw JWT access token.
            Marked as `repr=False` to avoid accidental logging.
    """
    token: str = field(repr=False)


@dataclass(kw_only=True)
class GetCurrentUserOutputDTO(UserOutputDTO):
    """Output DTO for current user retrieval.

    Inherits all fields (id, username, timezone, language) from UserOutputDTO,
    but acts as a unique type key for the CLI Registry.

    Attributes:
        message (str): Status message confirming retrieval.
            Defaults to "user_retrieved".
    """
    message: str = "user_retrieved"


class GetCurrentUserUseCase(UseCase[GetCurrentUserInputDTO, Optional[GetCurrentUserOutputDTO]]):
    """Use case for retrieving the current authenticated user from an access token.

    This use case validates a JWT access token and, if valid, resolves
    the corresponding user entity. If the token is expired, invalid,
    or the user does not exist, it returns None.
    """

    def __init__(
            self,
            uow_factory: UowFactoryType,
            clock: ClockProvider,
            token_provider: TokenProvider,
    ):
        """Initialize the GetCurrentUserUseCase.

        Args:
            uow_factory (UnitOfWork): Unit of Work factory for managing repositories and transactions.
            clock (ClockProvider): Provides current time for validation (not directly used here).
            token_provider (TokenProvider): Service for decoding and validating JWT tokens.
        """
        super().__init__(uow_factory, clock)
        self.token_provider = token_provider

    async def execute(self, request: GetCurrentUserInputDTO) -> Optional[UserOutputDTO]:
        """Validate the token and retrieve the current user.

        Steps:
            1. Decode and validate the token using the provider.
            2. Extract the username claim from the payload.
            3. Retrieve the user entity from the repository.
            4. Map the entity to an output DTO.

        Args:
            request (GetCurrentUserInputDTO): Input DTO containing the raw JWT string.

        Returns:
            Optional[UserOutputDTO]: The authenticated user as an output DTO,
            or None if the token is invalid, expired, or the user does not exist.
        """

        try:
            # 1. Technical validation of the token via provider
            payload: Dict = self.token_provider.decode_access_token(request.token)
        except (ExpiredTokenError, InvalidTokenError):
            return None

        username: str = payload.get("username")
        if not username:
            return None

        # 2. Existence and integrity validation
        async with self.uow as uow:
            user: User | None = await uow.users.get_by_username(username)
            if not user:
                return None

        # 3. Output mapping
        return UserMapper.to_output(user, dto_class=GetCurrentUserOutputDTO)
