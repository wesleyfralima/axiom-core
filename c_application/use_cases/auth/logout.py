from dataclasses import dataclass, field

from a_core import DTO
from b_domain.exceptions.security import NotAuthenticatedError
from b_domain.ports.providers import ClockProvider, TokenProvider
from b_domain.ports.use_case import UowFactoryType, UseCase

# ==========================================
# 1. DTOs de Entrada e Saída
# ==========================================


@dataclass(frozen=True)
class LogoutInputDTO(DTO):
    """Input DTO for logging out a user.

    This DTO encapsulates the data required to perform a logout
    operation: the access token the client holds, if any.

    Attributes:
        access_token (str | None): The client's access token, or None when
            the client has no session.
    """

    access_token: str | None = field(repr=False)


@dataclass(frozen=True)
class LogoutOutputDTO(DTO):
    """Output DTO for logout responses.

    This DTO represents the result of a logout operation, providing
    confirmation and a message for the client or presenter layer.

    Attributes:
        success (bool): Indicates whether the logout was successful.
        message (str): A status message describing the result.
        token_revoked (bool): Whether the token stopped being valid on the
            server side. When False, the session ends only because the client
            discards its token — which the client must do.
    """

    success: bool = True
    message: str = "logout_success"
    token_revoked: bool = False


# ==========================================
# 2. O Use Case
# ==========================================


class LogoutUseCase(UseCase[LogoutInputDTO, LogoutOutputDTO]):
    """Use case for logging out a user.

    Access tokens are stateless and there is no session store yet, so nothing
    is revoked here: logging out means the client discards its token, and the
    output says so (``token_revoked=False``). Real revocation (a denylist or
    a session table) belongs to the day a server exists (sync/web).

    The token is deliberately not validated: an expired or tampered token
    must still be discardable.
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
            LogoutOutputDTO: Confirmation, telling the client to discard the
                token.

        Raises:
            NotAuthenticatedError: If there is no token (nobody is logged in).
        """

        if not dto.access_token:
            raise NotAuthenticatedError()

        return LogoutOutputDTO(token_revoked=False)
