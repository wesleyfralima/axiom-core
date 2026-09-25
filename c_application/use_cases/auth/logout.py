from dataclasses import dataclass, field

from a_core import DTO
from b_domain.ports.providers import ClockProvider, TokenProvider
from b_domain.ports.use_case import UowFactoryType, UseCase

# ==========================================
# 1. DTOs de Entrada e Saída
# ==========================================


@dataclass(frozen=True)
class LogoutInputDTO(DTO):
    """Input DTO for logging out a user.

    This DTO encapsulates the data required to perform a logout
    operation. It contains the access token that must be invalidated
    or revoked to terminate the user's session.

    Attributes:
        access_token (str): The active access token to be invalidated.
    """

    access_token: str = field(repr=False)


@dataclass(frozen=True)
class LogoutOutputDTO(DTO):
    """Output DTO for logout responses.

    This DTO represents the result of a logout operation, providing
    confirmation and a message for the client or presenter layer.

    Attributes:
        success (bool): Indicates whether the logout was successful.
        message (str): A status message describing the result.
    """

    success: bool = True
    message: str = "logout_success"


# ==========================================
# 2. O Use Case
# ==========================================


class LogoutUseCase(UseCase[LogoutInputDTO, LogoutOutputDTO]):
    """Use case for logging out a user.

    This use case orchestrates the logout process, which typically involves:
    1. Decoding and validating the provided access token.
    2. Invalidating the token (e.g., adding it to a blacklist or
       removing the active session from persistent storage).

    It ensures that the user's session is properly terminated and
    communicates the result back via an output DTO.
    """

    def __init__(
        self,
        uow_factory: UowFactoryType,
        clock: ClockProvider,
        token_provider: TokenProvider,
    ):
        """Initialize the LogoutUseCase.

        Args:
            uow_factory (UowFactoryType): Factory for creating Unit of Work instances.
            clock (ClockProvider): Provider for time-related operations.
            token_provider (TokenProvider): Provider responsible for token validation
                and invalidation.
        """
        super().__init__(uow_factory, clock)
        self.token_provider = token_provider

    async def execute(self, dto: LogoutInputDTO) -> LogoutOutputDTO:
        """Execute the logout process.

        Args:
            dto (LogoutInputDTO): The input DTO containing the access token.

        Returns:
            LogoutOutputDTO: Confirmation that the logout was successful.
        """

        # TODO: Implement token invalidation logic (e.g., blacklist, session removal)

        return LogoutOutputDTO()
